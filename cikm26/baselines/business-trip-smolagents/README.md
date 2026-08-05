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

## Submit to TIRA

After the dataset has been uploaded, replace `DATASET-ID` with its TIRA ID:

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260805-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL OPENAI_REASONING_EFFORT \
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
