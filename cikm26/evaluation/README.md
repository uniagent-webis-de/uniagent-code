# cikm26 evaluation

A small, dockerized `click` CLI that evaluates a cikm26 submission by calling
the [`tira`](https://github.com/tira-io/tira) Python package's `Client.evaluate()` directly (the same method the `tira-cli evaluate` subcommand calls internally), and reports
the submission's compliance with the
[event-logging contract](../event-logging-contract/README.md) alongside the
task-specific measure(s).

It is compatible with both kinds of cikm26 spot-check datasets:

- **Task 2 "Solving"** datasets, such as
  [`../datasets/business-trip-spot-check/`](../datasets/business-trip-spot-check/README.md)
  (submission format `predictions.jsonl`, evaluated by `accuracy`), and
- **Task 1 "Retrieval"** datasets, such as
  [`../datasets/retrieval-de-spot-check/`](../datasets/retrieval-de-spot-check/README.md)
  (submission format `run.txt`/`run.txt.gz`, evaluated by `nDCG@10`).

`Client.evaluate()` looks up which measure(s) to compute from the dataset's
own trusted-evaluator configuration on TIRA, so this script does not
hardcode any task-specific evaluation logic; the `--dataset` you pass simply
selects the right dataset (and hence the right evaluator/measure) on TIRA's
side.

## What it adds on top of tira's `Client.evaluate()`

In addition to whatever measure(s) `Client.evaluate()` reports (e.g.
`accuracy` or `nDCG@10`), this script always adds:

- `model`: the LLM model used for the run, taken from the first
  non-placeholder `model` field found in the submission's
  `run-trace.jsonl.log.gz` event trace, or `"-"` if the trace has none (as is
  expected for model-free/deterministic submissions such as
  `business-trip-always-rejected` or the retrieval baselines).
- `valid_log_lines` / `invalid_log_lines`: how many lines of the run-trace
  log are (respectively, are not) valid events per the
  [event-logging contract](../event-logging-contract/README.md) — i.e. they
  decode as JSON, contain all required fields, and have a non-empty `model`
  and a `status` of `"ok"` or `"error"`. A missing run-trace log is reported
  as `0`/`0`, since logging may legitimately be skipped entirely for
  submissions that use no tools and no model calls (contract requirement 1).

## Usage

Build the image once:

```bash
docker build --tag cikm26-evaluation .
```

### Task 2 "Solving" example (business-trip)

```bash
docker run --rm --volume "$PWD/predictions:/predictions:ro" cikm26-evaluation \
  --predictions /predictions \
  --dataset business-trip-spot-check-20260907-training
```

### Task 1 "Retrieval" example

```bash
docker run --rm --volume "$PWD/predictions:/predictions:ro" cikm26-evaluation \
  --predictions /predictions \
  --dataset retrieval-de-spot-check-20260816-training
```

Both print a single JSON object, e.g.:

```json
{
  "accuracy": 0.83,
  "model": "gpt-oss-20b",
  "valid_log_lines": 214,
  "invalid_log_lines": 0
}
```

### Options

| Option | Required | Description |
| --- | --- | --- |
| `--predictions` | yes | Directory with the submission's output (`predictions.jsonl` or `run.txt`/`run.txt.gz`), and optionally its `run-trace.jsonl.log.gz` event trace. |
| `--dataset` | yes | The TIRA dataset ID to evaluate against, e.g. `business-trip-spot-check-20260907-training` or `retrieval-de-spot-check-20260816-training`. Dataset IDs are date-versioned; check the baselines' READMEs under [`../baselines/`](../baselines/) for the current ID. |
| `--truths` | no | Optional local truths directory. If omitted, tira downloads the dataset's published truths from TIRA. |
| `--run-trace` | no | Override the run-trace log path. Defaults to `<predictions>/run-trace.jsonl.log.gz`. |

## Requirements and network access

tira's `Client.evaluate()` needs network access to TIRA (to look up the dataset's
evaluator configuration and, unless `--truths` is given, its published
truths), and the underlying evaluators may need further network access on
first use:

- The business-trip datasets' `accuracy` measure uses HuggingFace's
  `evaluate` package, which downloads its metric script from the HuggingFace
  Hub unless it is already cached or the `OFFLINE=1` environment variable is
  set.
- The retrieval datasets' `nDCG@10` measure uses `trectools` (installed via
  the `tira[ir]` extra), which needs no extra network access beyond loading
  the (`qrels.txt`/`run.txt`) files themselves.

## Tests

```bash
docker build --tag cikm26-evaluation .
docker run --rm --volume "$PWD:/eval:ro" --workdir /eval --entrypoint python3 cikm26-evaluation \
  -m unittest discover -s /eval -p 'test_*.py'
```

The tests mock out tira's `Client.evaluate()` itself (network access to TIRA is not
assumed to be available), and instead focus on the log-analysis logic
(`analyze_run_trace`, `_is_valid_event`) and the CLI wiring.
