# Query Mining from Task 2 Agent Traces

Instructions for a coding agent that mines candidate retrieval queries from
the tool-call traces of Task 2 (solving) submissions. Participants' agents
issue searches/queries while solving applications; these are realistic
queries that can seed new retrieval topics.

Do not create a Python venv for this. Run any scripts in Docker (e.g. an
existing `.devcontainer/` or a stock `python:3.12` image with the repo
mounted), per the repository's `AGENTS.md`.

## 1. Download the submissions

Run from this directory (requires `tira-cli`, authenticated). Downloads go to
`submissions/` (gitignored, as it may contain participant data):

```bash
tira-cli download --all-submissions --dataset task-2-business-travel-20260928-test --output submissions
tira-cli download --all-submissions --dataset task-2-procurement-20260928-test --output submissions
tira-cli download --all-submissions --dataset task-2-expense-reimbursement-20260928-test --output submissions
```

Actual layout:
`submissions/raw-outputs/<dataset>/<run-timestamp>/output/run-trace.jsonl.log.gz`
(next to `predictions.jsonl`). The application type is the `<dataset>` part.

## 2. Workflow

Reference scripts for every step are in `scripts/`. Run them in Docker with this
directory mounted at `/d`, in order:

```bash
D="docker run --rm -v $PWD:/d python:3.12-slim"
$D python /d/scripts/extract.py     # steps 1-2
$D python /d/scripts/normalize.py   # step 3
$D sh -c "pip -q install scikit-learn numpy; python /d/scripts/cluster.py"  # step 4
$D python /d/scripts/select.py      # step 5 -> query-candidates.jsonl
```

Review the intermediate outputs between steps and adjust the filters/thresholds
(e.g. the tool list in `extract.py`, the case-text regex in `normalize.py`, the
`BAD` entity regex in `select.py`) when the data changes.

Write intermediate artifacts to `work/` (gitignored); the final result goes to
`query-candidates.jsonl` and is committed.

### Step 1: Find valid traces

For every `**/run-trace.jsonl.log.gz` under `submissions/`:

1. Decompress and parse each line as JSON.
2. Validate against `../../event-logging-contract/README.md`: all lines are
   valid JSON objects; required fields (`case_id`, `event_id`, `timestamp`,
   `event_type`, `model`, `status`) are present; the last event per `case_id`
   is a `decision`.
3. Record valid/invalid files, with the reason, in `work/trace-validation.tsv`
   (columns: `path`, `valid`, `reason`). Skip invalid files; do not repair
   them. Report the counts to the user.

### Step 2: Extract raw query candidates

From valid traces only, collect for each `tool_call` event (any `status`) the
string arguments in `input` that look like queries. Only use corpus-search
tools (currently `bm25`, `corpus_search`, `retrieve_corpus`, `retrieve_*`,
`search_rules`, `mounted_corpus.lexical_search`); ignore searches inside the case's own
documents (`search_case`), `grep` patterns, and file/fact-check tools. For new
or unfamiliar tool names, list tools and argument keys first and inspect examples.
Several tools fan one query out to multiple corpora, so deduplicate per
(submission, case, query) in step 3. Also consider
queries in `model_call` prompts only if clearly quoted as a search string.

Write one JSON line per raw query to `work/raw-queries.jsonl`:

```json
{"query": "...", "language": "de", "application_type": "business-travel", "case_id": "...", "submission": "<path>", "tool": "...", "event_id": "..."}
```

`application_type` comes from the dataset directory (business-travel,
procurement, expense-reimbursement). Detect `language` (de/en).

### Step 3: Normalize and filter

- Trim whitespace, collapse spaces, strip surrounding quotes; compare
  case-insensitively for deduplication but keep the original casing.
- Drop empty, very short (< 3 chars), very long (> 200 chars) strings,
  document/case identifiers, file names, and strings containing personal
  data of the applications (names, IBANs, addresses); drop queries that
  quote case text verbatim rather than asking an information need (OCR text,
  addresses, dates, many digits, company/university names of the cases,
  > 120 chars) and meta-instructions ("Prüfen, ob ...", "E05: ...").
- Keep the count of how often each normalized query occurs and the set of
  submissions and application types it occurs in.

### Step 4: Cluster

Group semantically equivalent or near-equivalent queries (paraphrases,
word-order variants, DE/EN translations of the same need):

1. Cluster with character n-gram TF-IDF and average-linkage agglomerative
   clustering (cosine distance threshold 0.65, `scripts/cluster.py`); a
   multilingual sentence-embedding model (in Docker) is a better but heavier
   option, needed to merge DE/EN translations.
2. Review every cluster; split or merge where the automatic result is wrong.
3. Choose one representative per cluster: the clearest, self-contained,
   natural query (prefer the most frequent among equally clear ones).
4. Save the clustering to `work/clusters.jsonl`
   (`cluster_id`, `representative`, `members`, `size`).

### Step 5: Select and write candidates

Keep clusters used by >= 2 submissions, top 100, ranked by number of distinct submissions, then by size. Prefer a diverse set (all three application
types, both languages, varied topics such as travel-expense limits,
procurement thresholds, reimbursement documents). Write
`query-candidates.jsonl`, one object per line:

```json
{"cluster_id": 3, "query": "...", "language": "de", "application_types": ["business-travel"], "num_queries": 12, "num_submissions": 5, "variants": ["...", "..."]}
```

Finally, summarize for the user: number of traces seen/valid, raw queries,
clusters, and candidates, plus notable problems (unusual tool names, invalid
logs). Candidates are suggestions only; a human must review them before they
become topics.

## Provenance

`query-candidates.jsonl` was derived with this workflow; how the last run went
is documented in [`query-candidates.provenance.md`](query-candidates.provenance.md).
