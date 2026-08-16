# Retrieval Baseline

This is the initial TIRA-compatible baseline scaffold for the UniAgent
retrieval task. It currently:

1. Loads a TIRA dataset or a local `ir_datasets` directory.
2. Reads the language from every query's raw `original_query` dictionary.
3. Verifies that all queries use the same language.
4. Can create a language-specific PyTerrier index.
5. Can retrieve all queries with BM25.
6. Writes the detected ISO language code to `language.txt`.

The Click command does not write the retrieval run yet.

The `create_index(dataset, language)` method creates a temporary PyTerrier
index with an English or German language pipeline. German indexing uses
`UTFTokeniser`, `GermanSnowballStemmer`, and `german-stopwords.txt`; English
indexing uses Terrier's English defaults.
`retrieve(dataset, index, language)` runs BM25 for every query and returns a
standard PyTerrier run DataFrame. Its `language` argument selects the matching
query tokenizer.

`german-stopwords.txt` contains Lucene's German Snowball stopword list,
normalized to Terrier's one-word-per-line format. See
`german-stopwords.NOTICE` for source and licensing information.

## Run locally

```bash
python baseline.py \
  --dataset ../../datasets/retrieval-en-spot-check \
  --output output
```

The same Click interface can be used by TIRA:

```bash
/baseline.py --dataset "$inputDataset" --output "$outputDir"
```

## Tests

```bash
PYTHONPATH=. pytest .
```

## Example Runs

"BM25, "DFIC", "DFIZ", "DirichletLM", "DLH", "DPH", "Hiemstra_LM", "LGD", "PL2", "TF_IDF"

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