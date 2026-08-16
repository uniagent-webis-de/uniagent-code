# Retrieval Baseline

This is the initial TIRA-compatible baseline scaffold for the UniAgent
retrieval task. It currently:

1. Loads the retrieval dataset via `ir_datasets` directory.
2. Reads the language (either german or english) from the query.
3. Creates a language-specific PyTerrier index.
4. Retrieves with a PyTerrier retrieval model.

## Submit to TIRA

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset retrieval-de-spot-check-20260816-training \
  --command '/app/baseline.py --dataset $inputDataset --wmodel BM25 --output $outputDir' \
  --dry-run
```

## Tests

```bash
PYTHONPATH=. pytest .
```

## Example Runs

```
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel BM25 --output runs/retrieval-de-spot-check/bm25
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel DFIC --output runs/retrieval-de-spot-check/dfic
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel DFIZ --output runs/retrieval-de-spot-check/dfiz
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel DirichletLM --output runs/retrieval-de-spot-check/dirichlet-lm
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel DLH --output runs/retrieval-de-spot-check/dlh
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel DPH --output runs/retrieval-de-spot-check/dph
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel Hiemstra_LM --output runs/retrieval-de-spot-check/hiemstra-lm
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel LGD --output runs/retrieval-de-spot-check/lgd
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel PL2 --output runs/retrieval-de-spot-check/pl2
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel TF_IDF --output runs/retrieval-de-spot-check/tf-idf

./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel BM25 --output runs/retrieval-en-spot-check/bm25
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel DFIC --output runs/retrieval-en-spot-check/dfic
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel DFIZ --output runs/retrieval-en-spot-check/dfiz
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel DirichletLM --output runs/retrieval-en-spot-check/dirichlet-lm
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel DLH --output runs/retrieval-en-spot-check/dlh
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel DPH --output runs/retrieval-en-spot-check/dph
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel Hiemstra_LM --output runs/retrieval-en-spot-check/hiemstra-lm
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel LGD --output runs/retrieval-en-spot-check/lgd
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel PL2 --output runs/retrieval-en-spot-check/pl2
./baseline.py --dataset ../../datasets/retrieval-en-spot-check/ --wmodel TF_IDF --output runs/retrieval-en-spot-check/tf-idf
```
