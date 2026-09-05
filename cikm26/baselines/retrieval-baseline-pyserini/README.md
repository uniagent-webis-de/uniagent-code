# Retrieval Baseline (Pyserini)

This is the Pyserini-based counterpart to the PyTerrier retrieval baseline
scaffold for the UniAgent retrieval task. It currently:

1. Loads the retrieval dataset via `ir_datasets` directory.
2. Reads the language (either german or english) from the query.
3. Creates a language-specific Lucene/Anserini index via Pyserini's
   `LuceneIndexer`, applying language-specific stemming and stopword removal
   automatically (via the `-language` option).
4. Retrieves with a Pyserini `LuceneSearcher` using BM25 or query likelihood
   with Dirichlet smoothing (QLD).


## Example Usage

```
./baseline.py --dataset ../../datasets/retrieval-de-spot-check/ --wmodel BM25 --output runs/retrieval-de-spot-check/bm25
```


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
