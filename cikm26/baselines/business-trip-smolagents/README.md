# Smolagents Business-Trip Baseline

This baseline uses smolagents tools and `OpenAIModel` with an OpenAI-compatible
endpoint to review every application independently. It exposes five tools:

1. `list_case_documents` inventories the PDFs.
2. `read_pdf` extracts layout-preserving text.
3. `search_case` returns cited snippets from all PDFs in the case.
4. `lookup_policy` retrieves a compact set of business-trip rules.
5. `check_facts` performs deterministic date, amount, overlap, and
   completeness checks.

Tools are restricted to the current case. The baseline fails explicitly if
the endpoint is unavailable or the agent returns malformed output; it does not
silently substitute a default label.

The five tools run in a deterministic evidence-collection pipeline before the
model is called. This avoids relying on native tool calls or generated code:
some OpenAI-compatible deployments of gpt-oss20 emit neither in the format
expected by `ToolCallingAgent` or `CodeAgent`. Every PDF is therefore read,
the case is searched, policies are loaded, and document completeness is
checked before the model receives the evidence and returns the final JSON.

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
docker build --tag business-trip-smolagents .
docker run --rm \
  --env OPENAI_BASE_URL \
  --env OPENAI_API_KEY \
  --env OPENAI_MODEL \
  --env OPENAI_REASONING_EFFORT \
  --volume "$PWD/../../datasets/business-trip-spot-check/inputs:/input:ro" \
  --volume "$PWD/output:/output" \
  business-trip-smolagents \
  --input /input \
  --output /output
```

## Event-trace logging

Every tool call (`list_case_documents`, `read_pdf`, `search_case`,
`lookup_policy`, `check_facts`) and every model call (the final decision) is
logged as one contract-compliant event, per
[`../../event-logging-contract/README.md`](../../event-logging-contract/README.md),
via `event_logging.py`.

`predict.py` writes these events as one gzip-compressed JSON object per line
to `run_trace.jsonl.gz` next to `predictions.jsonl` under `--output` (opened
once via `log_to_file()` at the start of the run, tagged with the configured
`OPENAI_MODEL` via `model_context()` for the whole run). The plain-text
progress messages `predict.py` prints go to stdout as before and are not
part of this file. Tests and other callers that don't use `log_to_file()`
get the JSONL lines on stdout instead (the default destination), e.g. pulled
out of a combined stdout stream with `zcat run_trace.jsonl.gz | jq` or
`grep '"tool":' | jq`.

Each case's events are chained via `parent_event_id` from its first tool
call through the final decision model call, and end in one `decision`
event — reconstructable as a per-`case_id` trace, as the contract requires.

Example lines (pretty-printed here; actually emitted as single lines):

```json
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0002", "parent_event_id": "evt-0001", "timestamp": "2026-09-07T17:30:12.345+00:00", "event_type": "tool_call", "model": "gpt-oss-20b", "tool": "read_pdf", "input": {"case_id": "dienstreiseantrag-01", "filename": "antrag-dienstreisegenehmigung.pdf"}, "output": "Jonas Ahlgrim Universitaet Kassel ...", "status": "ok", "error": null}
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0007", "parent_event_id": "evt-0006", "timestamp": "2026-09-07T17:30:14.201+00:00", "event_type": "model_call", "model": "gpt-oss-20b", "tool": null, "input": {"prompt": "..."}, "output": {"response": "{\"antrag\": \"dienstreiseantrag-01\", \"result\": \"genehmigt\", ...}"}, "status": "ok", "error": null}
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0008", "parent_event_id": "evt-0007", "timestamp": "2026-09-07T17:30:14.987+00:00", "event_type": "decision", "model": "gpt-oss-20b", "tool": null, "input": null, "output": {"antrag": "dienstreiseantrag-01", "result": "genehmigt", "begruendung": "..."}, "status": "ok", "error": null}
```

Field-by-field details (`case_id`, `event_id`, `parent_event_id`,
`timestamp`, `event_type`, `model`, `tool`, `input`, `output`, `status`,
`error`) are specified in the contract; `model` is always the run's
configured `OPENAI_MODEL`, on every event, not only `model_call`/`decision`
events.

## Submit to TIRA

After the dataset has been uploaded, replace `DATASET-ID` with its TIRA ID:

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260907-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```

## Tests

The tests exercise all five tools and output validation without calling an LLM:

```bash
docker build --tag business-trip-smolagents .
docker run --rm \
  --volume "$PWD/../..:/cikm26:ro" \
  --entrypoint python \
  business-trip-smolagents \
  -m unittest discover \
  -s /cikm26/baselines/business-trip-smolagents \
  -p 'test_*.py'
```
