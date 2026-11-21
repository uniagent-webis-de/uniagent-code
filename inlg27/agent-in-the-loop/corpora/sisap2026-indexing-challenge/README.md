# Runs and Evals.md

The file task2.zip contains the runs and the evals for task 2.

The file task3.zip contains the runs and the evals for task 3.

runs.json should be a superset etc.

# Evaluation Script:

The evaluation script is at https://github.com/sisap-challenges/sisap26-python-baseline/blob/main/eval.py.
You need to modify it slightly to make it self contained and runnable easily.

# Other enrichment files

These files support `../../corpus-enrichment/PROTOCOL_TO_SPLIT_SHARED_TASKS_INTO_SUBTASKS.md`.

- `code-repositories.json`: per paper id, the code repositories (`url`, evaluated `commit`, `branch`, `tasks`). Source: the [SISAP 2026 leaderboard](https://sisap-challenges.github.io/sisap26-leaderboard/leaderboard.html) data (repository column; commits/branches from the TIRA run metadata, `commit-in-paper` where given). Papers without a public repository have an empty list. `../../corpus-enrichment/create_code_archives.py` turns it into `code/<paper_id>/<repo>.zip` per subtask.
- `truths.json`: links to the truth (held-out evaluation data with gold standard) of task 2 and task 3.
- `llama-eval.h5` (task 2) and `nq-eval.h5` (task 3): the evaluation files **without the `train` collection**, i.e., only the queries and the gold standard (see below).

## `llama-eval.h5` and `nq-eval.h5`

The official files (`llama-eval/llama-eval.h5`, 134 MB; `nq-eval/nq-eval.h5`, 6.9 GB) are published at <https://huggingface.co/datasets/sisap-challenges/SISAP2026> (linked in `truths.json`). They embed the indexed collection (`train`) together with the queries and the gold standard. Because the collection is not needed to judge results, the `train` group was removed:

| File | Kept groups | Contents |
|---|---|---|
| `llama-eval.h5` | `test` | `queries` (1000×128, f32), `knns` (1000×100, i64), `dists` (1000×100, f64) |
| `nq-eval.h5` | `otest` | `queries` (sparse CSR: `data`, `indices`, `indptr`, attribute `shape` = 3452×30522), `knns` (3452×100, i32), `dists` (3452×100, f32) |

They were obtained without downloading the big files, by reading the remote HDF5 with HTTP range requests and copying everything except `train` (run in Docker, no venv):

```bash
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/w python:3.12 sh -c "
pip install -q --target /tmp/p h5py fsspec aiohttp requests &&
PYTHONPATH=/tmp/p python - <<'E'
import h5py, fsspec
base = 'https://huggingface.co/datasets/sisap-challenges/SISAP2026/resolve/main'
for name in ['llama-eval', 'nq-eval']:
    src = h5py.File(fsspec.open(f'{base}/{name}/{name}.h5', block_size=8*2**20).open(), 'r')
    with h5py.File(f'/w/{name}.h5', 'w') as dst:
        for k, v in src.attrs.items():
            dst.attrs[k] = v
        for k in src:
            if k != 'train':
                src.copy(k, dst)
E"
```

### How to use them

- Gold standard: `knns` has one row per query with the ids of the 100 true nearest neighbors (best first); ids are 1-based as in the challenge's result format. The challenge evaluated with k=30 for both tasks, so compare the first 30 columns. `dists` holds the matching gold-standard dot-product values.
- Evaluating a run: recall of a query = |returned k ids ∩ gold k ids| / k, averaged over queries (operating point: recall ≥ 0.8 for task 2, ≥ 0.9 for task 3). Result files follow the [challenge's format](https://sisap-challenges.github.io/2026/index.html#result_submission_format) (`knns`, `dists`, attributes `algo`, `task`, `buildtime`, `querytime`, `params`).
- Reading the sparse NQ queries: `scipy.sparse.csr_matrix((data, indices, indptr), shape=attrs['shape'])` from `otest/queries`.
- Anything that needs the indexed collection (re-running a system) needs the full files from Hugging Face.
