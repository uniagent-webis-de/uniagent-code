# Smolagents Business-Trip Baseline with Retrieval

This baseline extends `../business-trip-smolagents/` with retrieval-augmented
context from the background corpora shipped under
`inputs/retrieval-corpora/` (see the dataset README). It builds one BM25
retrieval tool per corpus using the same PyTerrier indexing approach as
`../retrieval-baseline-pyterrier/` (language-specific stemmer, stopwords, and
tokeniser), then folds the retrieved knowledge into the evidence package
handed to the model.

## Pipeline

`predict.py` runs in three phases:

1. **Scan all tasks.** `input_cases()` lists every `dienstreiseantrag-XX`
   application directory under `--input` (the `retrieval-corpora/` folder is
   excluded automatically since it has no PDFs directly inside it).
2. **Identify the key accept/reject aspects via retrieval, for every case.**
   `build_retrieval_tools()` discovers every
   `retrieval-corpora/<name>/documents.jsonl.gz`, and builds a dedicated tool
   per corpus, e.g. `retrieve_hessian_law_de`,
   `retrieve_university_kassel_public_de`, `retrieve_university_kassel_public_en`
   (an index is built once per corpus and reused for every case). For every
   case, `identify_key_aspects()` runs an iterative retrieval loop instead of
   a single fixed lookup:
   - Round 1 queries every corpus with the application text combined with a
     fixed set of rule keywords, then asks the model (via a dedicated
     aspect-analysis prompt, separate from the final decision prompt) to name
     the aspects that decide the case, each grounded in a concrete
     `(corpus, doc_id)` citation from the retrieved hits — the model may not
     invent rules that aren't in the retrieved text.
   - If the model reports an aspect as unclear, it provides a short follow-up
     query, which drives the next retrieval round instead of the fixed query;
     retrieval stops as soon as the model reports the aspects are
     sufficiently clear, or after `RETRIEVAL_MAX_ITERATIONS` rounds (2-3;
     see `predict.py`), whichever comes first — so the extra iterations are
     only spent when the aspects are genuinely unclear.
   - Once the loop stops, the case's key aspects (short title, finding, and
     citation) are printed to stdout so the retrieval basis for the decision
     is visible without inspecting the tool-call log.
3. **Decide with knowledge and key aspects included.** The case evidence
   (documents, search results, policies, completeness check — same as the
   non-retrieval baseline) is extended with an `external_knowledge` list of
   all ranked, cited corpus hits seen across the retrieval rounds and a
   `key_aspects` list of the aspects identified above; the model is
   instructed to ground its decision in `key_aspects` and their citations
   (i.e. the correct law/policy for the case) rather than rules it might
   otherwise recall imprecisely, and to decide `angenommen`/`abgelehnt` as
   before.

The dataset README notes that the final test set may ship additional or
larger corpora (for instance an intranet crawl) that are not present in the
spot-check. `build_retrieval_tools()` discovers corpora at runtime instead of
hard-coding the three known folders, so it also builds a tool for any future
corpus automatically; only the corpus language must be inferable from a
`-de`/`-en` folder suffix or a `language` document field.

## Tool-call logging

Every tool call (case-scoped `list_case_documents`/`read_pdf`/`search_case`,
the global `lookup_policy`/`check_facts`, and every `retrieve_<corpus>`) is
logged as one **JSON object per line** (JSON Lines / NDJSON) via
`tool_logging.py`, independent of how the tool is used.

`predict.py` writes these lines to `tool-calls.log` next to
`predictions.jsonl` under `--output` (opened once via `log_to_file()` at the
start of the run, so it captures tool calls from retrieval-tool building
onward). The plain-text progress messages `predict.py` prints (phase headers,
per-case summaries) go to stdout as before and are not part of this file.
Tests and other callers that don't use `log_to_file()` get the JSONL lines on
stdout instead (the default destination), e.g. pulled out of a combined
stdout stream with `grep '"tool":' | jq`.

Example lines (pretty-printed here; actually emitted as single lines):

```json
{"case_id": "dienstreiseantrag-01", "tool": "read_pdf", "arguments": {"case_id": "dienstreiseantrag-01", "filename": "antrag-dienstreisegenehmigung.pdf"}, "status": "ok", "error": null, "timestamp": "2026-09-07T17:30:12.345+00:00"}
{"case_id": "dienstreiseantrag-01", "tool": "retrieve_hessian_law_de", "arguments": {"query": "Lyon, FRANKREICH ...", "max_results": 5}, "status": "ok", "error": null, "timestamp": "2026-09-07T17:30:14.201+00:00"}
{"case_id": "dienstreiseantrag-03", "tool": "check_facts", "arguments": {"facts": {"kind": "compare_dates", "comparisons": [...]}}, "status": "error", "error": "Unsupported date operator: !=", "timestamp": "2026-09-07T17:30:15.009+00:00"}
```

### Line contract

Each line is a self-contained JSON object with the following fields:

| Field | Type | Description |
|---|---|---|
| `case_id` | string | The case active via `case_context()` when the call happened, or `"-"` if none was active. |
| `tool` | string | The tool's `name`, e.g. `read_pdf`, `retrieve_hessian_law_de`. |
| `arguments` | object | `forward()`'s parameters bound by name (see truncation rule below). |
| `status` | string | `"ok"` or `"error"`. |
| `error` | string \| null | `str(exception)` if `status == "error"`, else `null`. |
| `timestamp` | string | ISO-8601 UTC timestamp (millisecond precision) when the call finished. |

The log intentionally does not record return values: it is a transcript of
*which tool was called with what arguments, in which case, and whether it
succeeded*, not a cache of tool outputs.

**Truncation rule** (applied to each argument value): string values are
whitespace-normalised and cut to 200 characters with a trailing `…`. Other
JSON values (numbers, booleans, `null`, lists, dicts) are kept as native JSON
when their JSON encoding is at most 200 characters (so small structured
arguments like `check_facts`' `facts` object stay queryable, e.g.
`jq 'select(.arguments.facts.kind == "compare_dates")'`); larger ones fall
back to a truncated string preview of their JSON encoding. Errors are always
logged in full (not swallowed) so a failing call is never silently missing
from the log.

Because the tool is wrapped once in `build_tools()`/`build_retrieval_tools()`,
this works uniformly whether a tool is rebuilt per case (the case tools) or
built once and reused across all cases (the retrieval tools) — the shared
retrieval tools are simply tagged with whichever case is currently active
when they are called.

## Configuration

Set an OpenAI-compatible proxy or endpoint:

```bash
export OPENAI_BASE_URL=https://your-proxy.example/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=your-model
# Optional for reasoning models:
export OPENAI_REASONING_EFFORT=low
```

Use a dedicated, short-lived proxy credential rather than a production API
key. TIRA requires network access for this baseline.

## Run locally

```bash
docker build --tag business-trip-smolagents-with-retrieval .
docker run --rm \
  --env OPENAI_BASE_URL \
  --env OPENAI_API_KEY \
  --env OPENAI_MODEL \
  --env OPENAI_REASONING_EFFORT \
  --volume "$PWD/../../datasets/business-trip-spot-check/inputs:/input:ro" \
  --volume "$PWD/output:/output" \
  business-trip-smolagents-with-retrieval \
  --input /input \
  --output /output
```

## Submit to TIRA

After the dataset has been uploaded, replace `DATASET-ID` with its TIRA ID:

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260907-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```

## Tests

The tests build real BM25 indices over the shipped corpora and exercise the
full retrieval and evidence pipeline without calling an LLM. They require
Java/PyTerrier, so run them inside the Docker image, as for
`../retrieval-baseline-pyterrier/`:

```bash
docker build --tag business-trip-smolagents-with-retrieval .
docker run --rm \
  --volume "$PWD/../..:/cikm26:ro" \
  --entrypoint python3 \
  business-trip-smolagents-with-retrieval \
  -m unittest discover \
  -s /cikm26/baselines/business-trip-smolagents-with-retrieval \
  -p 'test_*.py'
```
