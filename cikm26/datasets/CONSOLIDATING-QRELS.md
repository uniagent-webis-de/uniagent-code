# Consolidating LLM Relevance Judgments

## Background

For each retrieval dataset we created four sets of raw relevance judgments (qrels), stored in `raw-qrels/`:

- `single-relevant`: the qrels the dataset was originally constructed with. A coding agent was instructed to find, for every query, one highly relevant document in the corpus; queries without such a document were removed. These are the most trustworthy judgments. Every query has at least one such document. **Note:** in the raw file these documents carry the score `1` (meaning "relevant"), but in the consolidated qrels they correspond to the highest grade, `3`.
- `gpt-oss-120b`, `gpt-oss-20b`, `qwen-2.5`: automatic judgments made with UMBRELA (graded 0–3) for every document in the top-100 pool of all submitted/baseline retrieval systems. These are noisy; the larger model is usually, but not always, more reliable.

`queries.jsonl` contains all information needs (`query`, plus `original_query.description` and `original_query.narrative`), and `documents.jsonl.gz` contains all documents (`doc_id`, `url`, `title`, `content`, ...).

```
documents.jsonl.gz
queries.jsonl
raw-qrels/
├── gpt-oss-120b/qrels.txt
├── gpt-oss-20b/qrels.txt
├── qwen-2.5/qrels.txt
└── single-relevant/qrels.txt
```

All qrels files use the TREC format `qid 0 doc_id score`.

## Task

Consolidate the four raw qrels into one `qrels.txt` (next to `documents.jsonl.gz` and `queries.jsonl`) and write a log `consolidation-relevance-judgments.log` (same directory).

### Grading scale

| Score | Meaning |
|-------|---------|
| 3 | Fully answers the information need; as relevant as the `single-relevant` document. |
| 2 | Clearly relevant and useful, but less complete or specific than a 3. |
| 1 | Only marginally relevant (e.g. related topic, partial or tangential information). Be strict: there must be a concrete reason to give a 1. |
| 0 | Not relevant. Explicitly written to `qrels.txt` for every candidate document you judged. |

Judge on the **content** of the document with respect to the query, its description, and its narrative. Do not average the model scores.

### Procedure (per query)

1. Read the query, description, and narrative.
2. Every `single-relevant` document gets score 3. Still read it and note in the log if it looks questionable (keep the 3 regardless; flag it for human review).
3. Collect all other candidate documents: those with a score > 0 in at least one of `gpt-oss-120b`, `gpt-oss-20b`, `qwen-2.5`. Documents with 0 in all three are not candidates: they are not judged by you and are not written to `qrels.txt`.
4. Read each candidate in `documents.jsonl.gz` and assign your own score (0–3). Treat the model scores as hints only, not as ground truth; if the models disagree, decide from the content. A document that is also in `single-relevant` is judged once (score 3).
5. Do not judge or add documents that are not candidates.

Every candidate must end up in `qrels.txt`, including those you grade 0 (e.g. all three models said relevant, but you decide it is not). A document that appears in `qrels.txt` with 0 was judged and found not relevant; a document that does not appear was not judged at all. This distinction matters, so never drop 0 entries.

Work query by query, append to the log after each query, and be resumable (skip queries that are already in the log). Batching by query or parallelising across queries is fine.

### Outputs

**`qrels.txt`**: TREC format `qid 0 doc_id score`, one line per judged document (all candidates and all `single-relevant` documents, scores 0–3), sorted by qid, then score (descending), then doc_id. No pretty-printing, no header.

**`consolidation-relevance-judgments.log`**: JSON Lines, one object per judged document:

```json
{"qid": 1, "doc_id": "...", "single_relevant": false, "gpt_oss_120b": 2, "gpt_oss_20b": 1, "qwen_2_5": 0, "final": 1, "reason": "One short sentence."}
```

Also log, as separate lines with `"type": "flag"`, `single-relevant` documents that look questionable.

### Validation (run before finishing)

- Every qid in `queries.jsonl` has at least one document with score 3 in `qrels.txt`.
- All doc_ids exist in `documents.jsonl.gz`; all qids exist in `queries.jsonl`.
- Every line of `qrels.txt` and the log parses, and every candidate has a line in `qrels.txt` (including 0s), every line of `qrels.txt` has a matching log entry (or is a `single-relevant` document).
- Report summary statistics: number of queries, and number of documents per score (including 0).

# Some examples from executions:

I did run those four instructions to consolidate the relevance judgments for our four test datasets:

```
Please run the "cikm26/datasets/CONSOLIDATING-QRELS.md" protocol on cikm26/datasets/in-progress/retrieval-hessian-law-de
```
Result: Started at 15 AIC, ended at:870 AIC.

```
Please run the "cikm26/datasets/CONSOLIDATING-QRELS.md" protocol on cikm26/datasets/in-progress/retrieval-kassel-intranet-de
```
Result: Started at 870 AIC, ended at 1167 AIC.

```
Please run the "cikm26/datasets/CONSOLIDATING-QRELS.md" protocol on cikm26/datasets/in-progress/retrieval-kassel-web-de
```
Result: Started at 1167 AIC, ended at 1412 AIC.

```
Please run the "cikm26/datasets/CONSOLIDATING-QRELS.md" protocol on cikm26/datasets/in-progress/retrieval-kassel-web-en
```
Result: Started at 1412 AIC, ended at  AIC.

It started multiple judgment subagents in parallel:

<img width="1555" height="867" alt="Screenshot_20261029_094845" src="https://github.com/user-attachments/assets/c6896d73-6242-4503-bc54-24f756231a64" />


The self-reports seem reasonable:


<img width="1881" height="711" alt="Screenshot_20261029_095445" src="https://github.com/user-attachments/assets/d993d05c-2dbb-4341-aaa6-0042758526ff" />

<img width="1880" height="210" alt="Screenshot_20261029_100802" src="https://github.com/user-attachments/assets/3b4a6893-83a9-490b-ab13-938a4654c15d" />
