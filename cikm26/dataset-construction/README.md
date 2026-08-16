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

## Create qrels with UMBRELA

UMBRELA requires Python 3.12 or newer:

```bash
python -m pip install -r requirements-umbrela.txt
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export OPENAI_MODEL=openai/gpt-oss-20b

python create_qrels.py \
  --dataset ../datasets/retrieval-en-spot-check/ \
  --runs ../baselines/retrieval-baseline/runs/retrieval-en-spot-check/ \
  --output qrels/retrieval-en-spot-check/gpt-oss-20b

python create_qrels.py \
  --dataset ../datasets/retrieval-de-spot-check/ \
  --runs ../baselines/retrieval-baseline/runs/retrieval-de-spot-check/ \
  --output qrels/retrieval-de-spot-check/gpt-oss-20b
```

The command creates `pools/`, `requests/`, and `responses/` below the output
directory and writes `qrels.txt`. Each topic is judged independently. A topic
is skipped when its persisted request and response both match the current
dataset and pool.

The `.devcontainer` uses Python 3.12 and Java 21 and installs the UMBRELA
cloud dependencies. Build it manually with:

```bash
docker build \
  --file .devcontainer/Dockerfile.dev \
  --tag uniagent-dataset-construction-dev \
  .
```
