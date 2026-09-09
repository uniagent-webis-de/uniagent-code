# Always-Rejected Business-Trip Baseline

This deterministic baseline emits `abgelehnt` for every application directory
in the TIRA input dataset.

Run it locally with:

```bash
python3 predict.py \
  --input ../../datasets/business-trip-spot-check/inputs \
  --output /tmp/business-trip-predictions
```

The output is `/tmp/business-trip-predictions/predictions.jsonl`.

## Event-logging contract

This baseline uses no tools and calls no model — it always predicts
`abgelehnt`. Per requirement 1 of
[`../../event-logging-contract/README.md`](../../event-logging-contract/README.md),
event-trace logging (`run_trace.jsonl.gz`) is therefore skipped entirely;
there are no tool calls or model calls worth tracing.

## Submit to TIRA

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260805-training \
  --command '/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```
