# Near-Duplicate Detection

We detect near-duplicate documents within each of the retrieval corpora in
[`../datasets/business-trip-spot-check/inputs/retrieval-corpora/`](../datasets/business-trip-spot-check/inputs/retrieval-corpora/)
with [CopyCat](https://github.com/chatnoir-eu/chatnoir-copycat), using its
`s3` similarity (word-8-gram overlap) with a threshold of `0.85`.

## Usage

Requires only `docker`. Run one of:

```
./run-hessian-law-de.sh
./run-university-kassel-public-de.sh
./run-university-kassel-public-en.sh
```

Each script writes `output/<corpus-name>/near-duplicates.jsonl`, one JSON
object per line, in CopyCat's native format:

```json
{"topic":"1","similarities":[{"firstId":"<doc-id-a>","secondId":"<doc-id-b>","similarities":{"s3":0.91}}, ...],"docs":<number of docs>}
```

`work/<corpus-name>/` holds intermediate artifacts (the converted documents,
the synthetic qrels file, and the Lucene index) and is reused/skipped on
re-runs so an interrupted run can be resumed cheaply (delete the relevant
subdirectory to force a rebuild of that step). Both `work/` and `output/` are
git-ignored.

Configuration (via environment variables, see `detect-near-duplicates.sh`):
`S3_THRESHOLD` (default `0.85`), `THREADS` (default: all cores), `JAVA_HEAP`
(default `8g`), `DOCKER_IMAGE` (default `webis/chatnoir-copycat:1.0-jupyter`).

## Runtime

CopyCat compares all documents of a corpus pairwise (O(n^2)) with s3, the
fastest of CopyCat's similarities in our benchmarks (~3,260 pairs/sec on a
16-core machine). Expect roughly:

| Corpus                        | Docs   | Pairs | Estimated runtime |
|--------------------------------|-------:|------:|-------------------|
| `hessian-law-de`                | 2,829  | ~4M   | ~20 min            |
| `university-kassel-public-en`   | 24,171 | ~292M | ~25 h              |
| `university-kassel-public-de`   | 30,983 | ~480M | ~41 h              |

Run the two large corpora detached on a server (e.g. `nohup ./run-....sh &`
or inside `tmux`/`screen`).

## How it works

1. Convert each corpus' `documents.jsonl.gz` (fields `doc_id`, `text`, ...)
   to CopyCat's expected `{"id": ..., "contents": ...}` jsonl, and a
   synthetic TREC qrels file that lists every document of the corpus under a
   single topic (`1 0 <doc-id> 1`). CopyCat deduplicates all documents of a
   topic pairwise, so this makes it compare the whole corpus.
2. Build a Lucene index over these documents with `IndexerMain.java`. We
   cannot use Anserini's own `io.anserini.index.IndexCollection` (bundled in
   the copycat-cli jar) here: the jar bundles two incompatible copies of
   Lucene side by side — Anserini's own unshaded, old Lucene 7.x, and a
   newer Lucene 8.x relocated to the `shaded.org.apache.lucene` package for
   CopyCat's own code. An index written with Anserini's indexer uses the
   unshaded Lucene 7.x codec and can not be opened by CopyCat's
   `AnseriniIndexDocumentResolver`, which reads indexes with the shaded
   Lucene 8.x classes. `IndexerMain.java` therefore builds the index
   directly with the shaded Lucene 8.x classes, storing the `id` and
   `contents` fields CopyCat's resolver expects.
3. The copycat-cli jar's `META-INF/services` Lucene SPI files (for `Codec`,
   `DocValuesFormat`, `PostingsFormat`) are broken (empty) because the
   maven-assembly-plugin `jar-with-dependencies` build does not merge
   `META-INF/services` entries from its dependencies — the last one wins.
   `detect-near-duplicates.sh` rewrites these files with the correct
   implementation class names before compiling/using the indexer.
4. Run CopyCat's `copy-cat` CLI (`--documents AnseriniIndex --similarities s3
   --s3Threshold 0.85 --runFile false`) against the qrels file and index.
