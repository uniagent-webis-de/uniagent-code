---
configs:
- config_name: inputs
  data_files:
  - split: train
    path:
    - "papers/**/**"
- config_name: truths
  data_files:
  - split: train
    path:
    - "manual-paper-summaries.jsonl"

tira_configs:
  resolve_inputs_to: "."
  resolve_truths_to: "."
  default_upload_name: "predictions.jsonl"
  input_format:
    name: "arbitrary"
  truth_format:
    name: "*.jsonl"
    config:
      id_field: "id"
      value_field: "summary"
      required_fields: ["id", "summary"]
      minimum_lines: 5
  baseline:
    link: "../../baseline-naive/"
    command: "/baseline.py --input $inputDataset --summary title-and-abstract --output ${outputDir}/predictions.jsonl"
    format:
      name: "*.jsonl"
  evaluator:
    image: "ghcr.io/uniagent-webis-de/agent-in-the-loop-evaluator:0.0.1"
    command: "/evaluate.py --predictions ${inputRun}/predictions.jsonl --truths ${inputDataset}/manual-paper-summaries.jsonl --results ${outputDir}"
---


```bash
tira-cli dataset-submission \
  --path touche-20-task-1-spot-check \
  --task inlg27-agent-in-the-loop \
  --split train \
  --dry-run
```
