#!/usr/bin/env python3

from pathlib import Path
import tempfile

import click
from tqdm import tqdm
import pandas as pd
import pyterrier as pt
from tira.third_party_integrations import ir_datasets

RETRIEVAL_CONFIGURATION = {
    "de": {
        "stemmer": pt.TerrierStemmer.german,
        "stopwords": Path(__file__)
        .with_name("german-stopwords.txt")
        .read_text(encoding="utf-8")
        .splitlines(),
        "tokeniser": pt.TerrierTokeniser.utf,
    },
    "en": {
        "stemmer": pt.TerrierStemmer.porter,
        "stopwords": pt.TerrierStopwords.terrier,
        "tokeniser": pt.TerrierTokeniser.english,
    },
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


def create_index(dataset, language: str):
    if language not in RETRIEVAL_CONFIGURATION:
        raise ValueError(f"Unsupported language: {language}")

    index_directory = Path(tempfile.mkdtemp(prefix="uniagent-retrieval_"))

    indexer = pt.IterDictIndexer(
        str(index_directory.resolve()),
        overwrite=True,
        meta={"docno": 100},
        verbose=True,
        **RETRIEVAL_CONFIGURATION[language],
    )
    index_ref = indexer.index(
        {
            "docno": str(document.doc_id),
            "text": document.default_text(),
        }
        for document in tqdm(list(dataset.docs_iter()), "Index documents")
    )
    return pt.IndexFactory.of(index_ref)


def retrieve(dataset, index, language: str) -> pd.DataFrame:
    if language not in RETRIEVAL_CONFIGURATION:
        raise ValueError(f"Unsupported language: {language}")

    tokeniser = pt.TerrierTokeniser.java_tokeniser(
        RETRIEVAL_CONFIGURATION[language]["tokeniser"]
    )
    topics = pd.DataFrame(
        [
            {
                "qid": str(query.query_id),
                "query": " ".join(tokeniser.getTokens(query.default_text())),
            }
            for query in dataset.queries_iter()
        ],
        columns=["qid", "query"],
    )
    if topics.empty:
        raise ValueError("Cannot retrieve because the dataset has no queries.")

    return pt.terrier.Retriever(index, wmodel="BM25", verbose=True).transform(topics)


@click.command()
@click.option(
    "--dataset",
    required=True,
    help="The TIRA dataset ID or local dataset directory.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, file_okay=False),
    help="The output directory.",
)
def main(dataset: str, output: Path) -> None:
    ir_dataset = ir_datasets.load(dataset)

    try:
        language = detect_query_language(ir_dataset)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Language: {language}")

    index = create_index(ir_dataset, language)
    run = retrieve(ir_dataset, index, language)

    output.mkdir(parents=True, exist_ok=True)
    pt.io.write_results(run, output / "run.txt.gz")


if __name__ == "__main__":
    main()
