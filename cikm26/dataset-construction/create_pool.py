#!/usr/bin/env python3

import json
from pathlib import Path

import click
from tira.third_party_integrations import ir_datasets
from trectools import TrecPoolMaker


def find_run_files(runs_directory: Path) -> list[Path]:
    run_files = sorted(
        path
        for path in runs_directory.rglob("*")
        if path.is_file() and path.name in {"run.txt", "run.txt.gz"}
    )
    if not run_files:
        raise ValueError(f"No run.txt or run.txt.gz files found in {runs_directory}.")
    return run_files


def create_pool(dataset, run_files: list[Path], k: int) -> list[dict[str, str]]:
    if k < 1:
        raise ValueError("k must be at least 1.")

    pool = TrecPoolMaker().make_pool_from_files(
        [str(path) for path in run_files],
        strategy="topX",
        topX=k,
    )
    queries = {str(query.query_id) for query in dataset.queries_iter()}
    documents = dataset.docs_store()
    records = []

    for qid, docnos in sorted(pool.pool.items(), key=lambda item: str(item[0])):
        qid = str(qid)
        if qid not in queries:
            raise ValueError(f"Run contains unknown query ID: {qid}")

        for docno in sorted(docnos):
            docno = str(docno)
            if documents.get(docno) is None:
                raise ValueError(f"Run contains unknown document ID: {docno}")
            records.append({"qid": qid, "docno": docno})

    return records


def write_pool(records: list[dict[str, str]], output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_file = output_directory / "pool.jsonl"
    output_file.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return output_file


@click.command()
@click.option(
    "--dataset",
    required=True,
    help="The TIRA dataset ID or local ir_datasets directory.",
)
@click.option(
    "--runs",
    required=True,
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    help="Directory containing run.txt or run.txt.gz files.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, file_okay=False),
    help="Directory in which pool.jsonl is written.",
)
@click.option(
    "--k",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of top documents pooled per query and run.",
)
def main(dataset: str, runs: Path, output: Path, k: int) -> None:
    try:
        records = create_pool(
            ir_datasets.load(dataset),
            find_run_files(runs),
            k,
        )
        output_file = write_pool(records, output)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Wrote {len(records):,} pooled query-document pairs to {output_file}.")


if __name__ == "__main__":
    main()
