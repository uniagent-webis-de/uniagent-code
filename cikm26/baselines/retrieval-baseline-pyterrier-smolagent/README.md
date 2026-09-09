# Retrieval Baseline (Smolagents, Self-Evaluating)

This extends `../retrieval-baseline-pyterrier/`'s PyTerrier BM25 pipeline
(same language-specific stemmer/stopwords/tokeniser and indexing code) with a
small agent that judges and improves its own queries before producing the
final run, using three tools (`retrieval_tools.py`):

1. **`judge_relevance`** — asks the model to make up to 20 of its own graded
   relevance judgments (0-3) for a query, over the top candidates retrieved
   for it. These judgments act as a tiny, run-specific qrels file; they are
   made once per query (from the first retrieval round) and reused for
   every reformulation tried afterwards.
2. **`compute_ndcg`** — deterministically scores any ranked list of document
   IDs with nDCG@10 against the judgments from (1). No model call; pure
   arithmetic, so it is cheap to call once per candidate query.
3. **`reformulate_query`** — asks the model to propose a new formulation of
   the query, given the original query, the previously tried query, and its
   nDCG@10 score, and whether the model is already satisfied.

## Pipeline

`baseline.py`'s `run_agentic_retrieval()` runs, per query:

1. Retrieve with the query's original text.
2. Judge up to 20 of the retrieved candidates via `judge_relevance` (first
   round only).
3. Score the ranking with `compute_ndcg` against those judgments.
4. If nDCG@10 has not converged and `--max-reformulations` rounds are not
   yet exhausted, ask `reformulate_query` for a new query and repeat from
   step 1; stop early if the model reports it is `satisfied`.
5. Take whichever query text achieved the best nDCG@10 across all rounds,
   and move the documents judged relevant (relevance > 0) to the top of
   that query's ranking via `reorder_with_relevant_first()`, preserving the
   existing BM25 order both among the promoted documents and among the
   rest.

The final, reordered ranking for every query is written to `run.txt.gz` as
usual.

## Event-trace logging

Every `judge_relevance`/`compute_ndcg`/`reformulate_query` call (including
the model calls nested inside `judge_relevance`/`reformulate_query`), each
retrieval round's outcome (`observation`), and the query's final chosen
query/nDCG/relevant-count (`decision`) are logged as one contract-compliant
event per
[`../../event-logging-contract/README.md`](../../event-logging-contract/README.md),
via `event_logging.py` (same module as
`../business-trip-smolagents-with-retrieval/`). Events are written as one
gzip-compressed JSON object per line to `run-trace.jsonl.log.gz` next to
`run.txt.gz` under `--output`. Indexing/retrieval resource consumption is
still tracked separately via `tirex_tracker` into
`index-ir-metadata.yml`/`retrieval-ir-metadata.yml`.

## Configuration

Set an OpenAI-compatible proxy or endpoint:

```bash
export OPENAI_BASE_URL=https://your-proxy.example/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=your-model
```

Use a dedicated, short-lived proxy credential rather than a production API
key.

## Example Usage

```bash
docker build --tag retrieval-baseline-pyterrier-smolagent .
docker run --rm \
  --env OPENAI_BASE_URL --env OPENAI_API_KEY --env OPENAI_MODEL \
  --volume "$PWD/../../datasets/retrieval-de-spot-check:/input:ro" \
  --volume "$PWD/runs/retrieval-de-spot-check:/output" \
  retrieval-baseline-pyterrier-smolagent \
  --dataset /input --max-reformulations 2 --output /output
```

## Submit to TIRA

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset retrieval-de-spot-check-20260816-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/baseline.py --dataset $inputDataset --max-reformulations 2 --output $outputDir' \
  --dry-run
```

## Tests

The tests build real PyTerrier indices and exercise `judge_relevance`,
`compute_ndcg`, `reformulate_query`, and the final reordering with a
scripted mock model (no live LLM call). They require Java/PyTerrier, so run
them inside the Docker image, as for `../retrieval-baseline-pyterrier/`:

```bash
docker build --tag retrieval-baseline-pyterrier-smolagent .
```

(the build already runs `PYTHONPATH=. pytest .`; or run it standalone
inside a container started from the image, same as the other PyTerrier
baselines).
