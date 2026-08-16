# Dataset Construction

Create a depth-100 pool from all `run.txt` and `run.txt.gz` files below a
runs directory:

```bash
python create_pool.py \
  --dataset ../datasets/retrieval-en-spot-check/ \
  --runs ../baselines/retrieval-baseline/runs/retrieval-en-spot-check/ \
  --output pools/retrieval-en-spot-check/
```

The script uses `trectools.TrecPoolMaker` with the `topX` strategy and writes
the pool dictionary to `OUTPUT/top-100-pool.json`. Each query ID maps to its
list of pooled document IDs. Change the pooling depth and filename with `--k`.
