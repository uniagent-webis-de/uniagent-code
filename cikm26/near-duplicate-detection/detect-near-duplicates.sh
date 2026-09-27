#!/usr/bin/env bash
# Detect near-duplicate documents in a retrieval corpus with CopyCat
# (https://github.com/chatnoir-eu/chatnoir-copycat), using the s3 similarity
# (word-8-gram overlap) on all documents of the corpus.
#
# This is a shared driver script; the per-corpus entry points are
# run-<corpus-name>.sh. It runs everything (index building + deduplication)
# inside the `webis/chatnoir-copycat:1.0-jupyter` docker container, so the
# only requirement on the host/server is `docker`.
#
# Usage: ./detect-near-duplicates.sh <corpus-name>
#
# Environment variables (all optional):
#   S3_THRESHOLD   near-duplicate s3-score threshold (default: 0.85)
#   THREADS        number of threads to use inside the container (default: nproc)
#   JAVA_HEAP      max JVM heap for indexing/deduplication (default: 8g)
#   DOCKER_IMAGE   CopyCat docker image (default: webis/chatnoir-copycat:1.0-jupyter)
#
# Note on runtime: CopyCat compares all documents of the corpus pairwise
# (O(n^2)), so this can run for many hours on large corpora (tens of
# thousands of documents). Run it detached, e.g. with `nohup ... &` or
# `tmux`/`screen`, on a server.
set -euo pipefail

CORPUS_NAME="${1:?Usage: $0 <corpus-name>}"

S3_THRESHOLD="${S3_THRESHOLD:-0.85}"
THREADS="${THREADS:-$(nproc)}"
JAVA_HEAP="${JAVA_HEAP:-8g}"
DOCKER_IMAGE="${DOCKER_IMAGE:-webis/chatnoir-copycat:1.0-jupyter}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CORPUS_DIR="${REPO_ROOT}/cikm26/datasets/business-trip-spot-check/inputs/retrieval-corpora/${CORPUS_NAME}"
INPUT_GZ="${CORPUS_DIR}/documents.jsonl.gz"

if [ ! -f "${INPUT_GZ}" ]; then
	echo "Could not find corpus documents at ${INPUT_GZ}" >&2
	exit 1
fi

WORK_DIR="${SCRIPT_DIR}/work/${CORPUS_NAME}"
OUTPUT_DIR="${SCRIPT_DIR}/output/${CORPUS_NAME}"
mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}"

echo "Deduplicating corpus '${CORPUS_NAME}' (s3 threshold=${S3_THRESHOLD}, threads=${THREADS}, heap=${JAVA_HEAP})"

docker run --rm \
	-e _JAVA_OPTIONS="-Xmx${JAVA_HEAP}" \
	-v "${REPO_ROOT}:/repo" \
	-v "${SCRIPT_DIR}:/ndd" \
	"${DOCKER_IMAGE}" bash -c "
set -euo pipefail

WORK=/ndd/work/${CORPUS_NAME}
OUT=/ndd/output/${CORPUS_NAME}
JAR=/copycat/copycat-cli-1.0-SNAPSHOT-jar-with-dependencies.jar

# --- 1. Convert the corpus to CopyCat's expected {id, contents} jsonl, and
#        build a synthetic qrels file that lists every document under a
#        single topic (CopyCat deduplicates all documents of a topic pairwise).
if [ ! -f \"\${WORK}/contents.jsonl\" ] || [ ! -f \"\${WORK}/qrels.txt\" ]; then
	echo 'Preparing input documents and qrels file...'
	python3 - <<'PY'
import gzip
import json

corpus_name = '${CORPUS_NAME}'
work = '${WORK_DIR}'
input_gz = '/repo/cikm26/datasets/business-trip-spot-check/inputs/retrieval-corpora/' + corpus_name + '/documents.jsonl.gz'

with gzip.open(input_gz, 'rt', encoding='utf-8') as fin, \\
     open('/ndd/work/' + corpus_name + '/contents.jsonl', 'w', encoding='utf-8') as f_contents, \\
     open('/ndd/work/' + corpus_name + '/qrels.txt', 'w', encoding='utf-8') as f_qrels:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        doc_id = doc['doc_id']
        f_contents.write(json.dumps({'id': doc_id, 'contents': doc['text']}) + '\\n')
        f_qrels.write('1 0 ' + doc_id + ' 1\\n')
PY
	echo \"Wrote \$(wc -l < \${WORK}/contents.jsonl) documents.\"
fi

# --- 2. Fix the copycat-cli jar's broken Lucene SPI service files (the
#        maven-assembly-plugin jar-with-dependencies build does not merge
#        META-INF/services files, so the last one wins and Codec/DocValuesFormat
#        end up empty), then compile our custom shaded-Lucene indexer.
if [ ! -d \"\${WORK}/index\" ] || [ -z \"\$(ls -A \${WORK}/index 2>/dev/null)\" ]; then
	echo 'Building Lucene index...'
	rm -rf /tmp/exploded-jar && mkdir -p /tmp/exploded-jar
	(cd /tmp/exploded-jar && unzip -q -o \"\${JAR}\")
	printf 'org.apache.lucene.codecs.lucene60.Lucene60Codec\\norg.apache.lucene.codecs.lucene62.Lucene62Codec\\norg.apache.lucene.codecs.lucene70.Lucene70Codec\\n' \\
		> /tmp/exploded-jar/META-INF/services/org.apache.lucene.codecs.Codec
	printf 'org.apache.lucene.codecs.lucene54.Lucene54DocValuesFormat\\norg.apache.lucene.codecs.lucene70.Lucene70DocValuesFormat\\n' \\
		> /tmp/exploded-jar/META-INF/services/org.apache.lucene.codecs.DocValuesFormat
	printf 'org.apache.lucene.codecs.lucene50.Lucene50PostingsFormat\\norg.apache.lucene.search.suggest.document.Completion50PostingsFormat\\n' \\
		> /tmp/exploded-jar/META-INF/services/org.apache.lucene.codecs.PostingsFormat

	mkdir -p \${WORK}/classes
	javac -cp \"\${JAR}\" -d \${WORK}/classes /ndd/IndexerMain.java
	rm -rf \${WORK}/index && mkdir -p \${WORK}/index
	java -cp \"\${WORK}/classes:\${JAR}\" IndexerMain \"\${WORK}/contents.jsonl\" \"\${WORK}/index\"
else
	echo 'Index already exists, skipping index build.'
fi

# --- 3. Run CopyCat's deduplication CLI (skips if output already exists).
mkdir -p \${OUT}
if [ -f \"\${OUT}/near-duplicates.jsonl\" ]; then
	echo \"\${OUT}/near-duplicates.jsonl already exists, skipping deduplication.\"
else
	echo 'Running CopyCat deduplication (this can take a long time for large corpora)...'
	copy-cat \\
		--input \"\${WORK}/qrels.txt\" \\
		--output \"\${OUT}/near-duplicates.jsonl\" \\
		--documents AnseriniIndex \\
		--anseriniIndex \"\${WORK}/index\" \\
		--similarities s3 \\
		--s3Threshold ${S3_THRESHOLD} \\
		--ranks 1000000 \\
		--runFile false \\
		--threads ${THREADS}
fi

echo 'Done. Near-duplicate pairs written to' \${OUT}/near-duplicates.jsonl
"
