#!/usr/bin/env python3

import gzip
import tempfile
from pathlib import Path

import click
import pandas as pd
from tqdm import tqdm
from tira.third_party_integrations import ir_datasets

# We use the tracker to monitor resource consumption etc. of the indexing and retrieval.
# The tracking is optional, i.e., you can remove it or switch to an alternative such as repro_eval.
from tirex_tracker import tracking

# Pyserini (via Anserini) ships language-specific Lucene analyzers (stemming and
# stopword removal) for each of these ISO language codes, applied automatically
# to both the index and the queries via the "-language"/set_language options.
SUPPORTED_LANGUAGES = {"de", "en"}

WMODEL_CONFIGURATION = {
    "BM25": lambda searcher: searcher.set_bm25(),
    "QLD": lambda searcher: searcher.set_qld(),
}


def detect_query_language(dataset) -> str:
    languages = set()
    query_count = 0

    for query in dataset.queries_iter():
        query_count += 1
        original_query = query.original_query
        if not isinstance(original_query, dict):
            raise ValueError(
                f"Query {query.query_id} does not provide an original_query dictionary."
            )

        language = original_query.get("language")
        if not isinstance(language, str) or not language.strip():
            raise ValueError(
                f"Query {query.query_id} does not provide a valid language."
            )
        languages.add(language)

    if query_count == 0:
        raise ValueError("Cannot detect a language because the dataset has no queries.")
    if len(languages) != 1:
        raise ValueError(
            "Expected all queries to have one language, found: "
            + ", ".join(sorted(languages))
        )

    return languages.pop()


def create_index(dataset, language: str, output_dir: Path | None = None) -> Path:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")

    from pyserini.index.lucene import LuceneIndexer

    index_directory = Path(tempfile.mkdtemp(prefix="uniagent-retrieval_"))
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="uniagent-index-metadata_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    docs_to_index = [
        {"id": str(document.doc_id), "contents": document.default_text()}
        for document in tqdm(list(dataset.docs_iter()), "Index documents")
    ]

    indexer = LuceneIndexer(
        args=[
            "-index",
            str(index_directory.resolve()),
            "-language",
            language,
            "-storePositions",
            "-storeDocvectors",
            "-storeRaw",
        ]
    )

    with tracking(export_file_path=output_dir / "index-ir-metadata.yml"):
        if docs_to_index:
            indexer.add_batch_dict(docs_to_index)
        indexer.close()

    return index_directory


def write_run(run: pd.DataFrame, output_file: Path) -> None:
    with gzip.open(output_file, "wt", encoding="utf-8") as file:
        for _, row in run.iterrows():
            file.write(
                f"{row['qid']} Q0 {row['docno']} {row['rank']} {row['score']} pyserini\n"
            )


def retrieve(
    dataset,
    index_directory: Path,
    language: str,
    wmodel: str = "BM25",
    output: Path | None = None,
) -> pd.DataFrame:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    if wmodel not in WMODEL_CONFIGURATION:
        raise ValueError(f"Unsupported retrieval model: {wmodel}")

    from pyserini.search.lucene import LuceneSearcher

    queries = [
        {"qid": str(query.query_id), "query": query.default_text()}
        for query in dataset.queries_iter()
    ]
    if not queries:
        raise ValueError("Cannot retrieve because the dataset has no queries.")

    if output is None:
        metadata_directory = Path(
            tempfile.mkdtemp(prefix="uniagent-retrieval-metadata_")
        )
    else:
        output.mkdir(parents=True, exist_ok=True)
        metadata_directory = output

    searcher = LuceneSearcher(str(index_directory.resolve()))
    searcher.set_language(language)
    WMODEL_CONFIGURATION[wmodel](searcher)

    rows = []
    with tracking(export_file_path=metadata_directory / "retrieval-ir-metadata.yml"):
        for query in tqdm(queries, "Retrieve"):
            hits = searcher.search(query["query"], k=1000)
            for rank, hit in enumerate(hits, start=1):
                rows.append(
                    {
                        "qid": query["qid"],
                        "docno": hit.docid,
                        "rank": rank,
                        "score": hit.score,
                    }
                )

    ret = pd.DataFrame(rows, columns=["qid", "docno", "rank", "score"])
    if output is not None:
        write_run(ret, output / "run.txt.gz")
    return ret


@click.command()
@click.option(
    "--dataset",
    required=True,
    help="The TIRA dataset ID or local dataset directory.",
)
@click.option(
    "--wmodel",
    default="BM25",
    show_default=True,
    help="The retrieval model for Pyserini.",
    type=click.Choice(["BM25", "QLD"]),
)
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, file_okay=False),
    help="The output directory.",
)
def main(dataset: str, output: Path, wmodel: str) -> None:
    ir_dataset = ir_datasets.load(dataset)

    try:
        language = detect_query_language(ir_dataset)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    output.mkdir(parents=True, exist_ok=True)
    (output / "language.txt").write_text(f"{language}\n", encoding="utf-8")
    click.echo(f"Detected query language: {language}")

    index_directory = create_index(ir_dataset, language, output)
    retrieve(ir_dataset, index_directory, language, wmodel, output)


if __name__ == "__main__":
    main()
