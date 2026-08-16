---
configs:
- config_name: inputs
  data_files:
  - split: train
    path: ["queries.jsonl", "documents.jsonl.gz"]
- config_name: truths
  data_files:
  - split: train
    path: ["qrels.txt", "queries.jsonl"]

tira_configs:
  resolve_inputs_to: "."
  resolve_truths_to: "."
  default_upload_name: "run.txt.gz"
  baseline:
    link: ../../../baselines/retrieval-baseline/
    command: /app/baseline.py --dataset $inputDataset --output $outputDir --wmodel BM25 
    format:
      name: ["run.txt"]
  input_format:
    name: arbitrary
  truth_format:
    name: "qrels.txt"
  evaluator:
    measures: ["nDCG@10"]
---

# UniAgent 2026 Retrieval: Spot-Check Dataset for Retrieval in German

This uses the public crawl of the University of Kassel (only documents in german language) and some LLM-generated queries and qrels to verify that everything works. Attention: while the documents are from a valid crawl (the real test set will then only in addition also contain documents that are only available in the intranet), the queries and relevance judgments are fully synthetic. Hence, it is unclear how an evaluation on this dataset is meaningful or not.

```
tira-cli dataset-submission --path retrieval-de-spot-check/ --task uniagent --split train --dry-run
```

