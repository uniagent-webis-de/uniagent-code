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
2. **Retrieve from every corpus for every case.** `build_retrieval_tools()`
   discovers every `retrieval-corpora/<name>/documents.jsonl.gz`, and builds a
   dedicated tool per corpus, e.g. `retrieve_hessian_law_de`,
   `retrieve_university_kassel_public_de`, `retrieve_university_kassel_public_en`
   (an index is built once per corpus and reused for every case). For every
   case, a query combining the application text with a fixed set of rule
   keywords is sent to all retrieval tools, and the ranked hits from all
   corpora are merged by score.
3. **Decide with knowledge included.** The case evidence (documents, search
   results, policies, completeness check — same as the non-retrieval baseline)
   is extended with an `external_knowledge` list of ranked, cited corpus hits,
   and the model is asked to decide `angenommen`/`abgelehnt` as before.

The dataset README notes that the final test set may ship additional or
larger corpora (for instance an intranet crawl) that are not present in the
spot-check. `build_retrieval_tools()` discovers corpora at runtime instead of
hard-coding the three known folders, so it also builds a tool for any future
corpus automatically; only the corpus language must be inferable from a
`-de`/`-en` folder suffix or a `language` document field.

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
  --dataset business-trip-spot-check-20260805-training \
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
