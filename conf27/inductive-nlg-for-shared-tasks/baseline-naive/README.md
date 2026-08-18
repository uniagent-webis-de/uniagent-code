# Naive Baseline

This deterministic baseline extracts each `paper.txt.md` title and abstract.

```bash
python3 baseline.py \
  --input ../corpora-in-progress/touche-20-task-1-spot-check/papers \
  --output predictions.jsonl \
  --summary title-and-abstract
```

`--summary` accepts `title`, `abstract`, or `title-and-abstract`. The output
contains one JSON object per line:

```json
{"id": "172", "summary": "Argument Retrieval Using Deep Neural Ranking Models"}
```
