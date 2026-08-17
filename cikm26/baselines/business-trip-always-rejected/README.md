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

## Submit to TIRA

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260805-training \
  --command '/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```
