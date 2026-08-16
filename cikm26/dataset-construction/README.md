# Dataset Construction

Create a depth-100 pool from all `run.txt` and `run.txt.gz` files below a
runs directory:

```bash
python create_pool.py \
  --dataset ../../datasets/retrieval-en-spot-check/ \
  --runs ../baselines/retrieval-baseline/runs/retrieval-en-spot-check/ \
  --output pools/retrieval-en-spot-check/
```

The script uses `trectools.TrecPoolMaker` with the `topX` strategy and writes
one `{"qid": ..., "docno": ...}` object per pooled pair to
`OUTPUT/pool.jsonl`. Change the pooling depth with `--k`.
