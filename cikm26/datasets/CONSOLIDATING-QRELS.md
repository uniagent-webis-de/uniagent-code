# Consolidating LLM Relevance Judgments

We did create four set of relevance judgments (qrels). single-relevant are qrels for which the dataset was originally constructed. I.e., an Coding Agent (Claude Sonnet 5.5) was instructed to find for every query one highly relevant document in the corpus, if no such document was found, than the query was removed. Those qrels are in the single-relevant dircetory and should be considered as the most relevant. After collecting all retrieval solutions, we created a top-100 pool and used GPT-OSS-120b, GPT-OSS-20b, and Qwen2.5-7b to make relevance judgments with UMBRELA for all documents in the top-100 pool. Those qrels are on the gpt-oss-120b, gpt-oss-20b, and qwen-2.5 directories.

Additionally, the `queries.jsonl` contains all information needs, and `documents.jsonl.gz` contains all documents.

The directory structure is therefore:

```
documents.jsonl.gz
queries.jsonl
raw-qrels/
├── gpt-oss-120b
│   └── qrels.txt
├── gpt-oss-20b
│   └── qrels.txt
├── qwen-2.5
│   └── qrels.txt
└── single-relevant
    └── qrels.txt
```

Your task is to consolidate those four qrels into a single qrels.txt file. (stored next to documents.jsonl.gz and queries.jsonl)
For each query, assume that the documents relevant from single-relevant get the highest score of 3, but please still look at this document. Then, look at each document that is judged with higher than 0 from any fo the gpt-oss-120b, gpt-oss-20b, or qwen-2.5 qrels. Critically question those judgments, and create your judgments, a document should get 1, if it is slightly relevant (you should not be too positive, there should be a reason to give a 1), a score of 2 if it is more relevant, and 3 if it is as relevant as the document from single-relevant. Persist a log into consolidation-relevance-judgments.log
