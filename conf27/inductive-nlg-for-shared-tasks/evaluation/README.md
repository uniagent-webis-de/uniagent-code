# Summary Evaluation

The evaluator matches predictions and references by `id` and reports BLEU,
chrF, ROUGE-1, ROUGE-2, and ROUGE-L.

```bash
python3 evaluate.py \
  --predictions ../baseline-naive/foo.jsonl \
  --truths ../corpora/touche-20-task-1-spot-check/manual-paper-summaries.jsonl \
  --results results
```

The command writes `results/evaluation.prototext`. BLEU and chrF use a
0–100 scale; ROUGE values are mean per-document F-scores on a 0–1 scale.
