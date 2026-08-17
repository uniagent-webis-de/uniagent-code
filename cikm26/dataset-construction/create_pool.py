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


def get_pool(
    runs_directory: Path, k: int, output_directory: Path
) -> dict[str, list[str]]:
    output_file = output_directory / f"top-{k}-pool.json"
    if output_file.is_file():
        click.echo(f"Load existing pool from {output_file}.")
        with output_file.open(encoding="utf-8") as file:
            return json.load(file)

    if k < 1:
        raise ValueError("k must be at least 1.")

    run_files = find_run_files(runs_directory)
    click.echo(f"Create top-{k} pool from {len(run_files)} runs.")
    pool = TrecPoolMaker().make_pool_from_files(
        [str(path) for path in run_files],
        strategy="topX",
        topX=k,
    )
    pool_dictionary = {
        str(qid): sorted(str(docno) for docno in docnos)
        for qid, docnos in sorted(pool.pool.items(), key=lambda item: str(item[0]))
    }

    output_directory.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(pool_dictionary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return pool_dictionary


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
    help="Directory in which the top-k pool JSON file is written.",
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
        ir_datasets.load(dataset)
        pool = get_pool(runs, k, output)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    pool_size = sum(len(documents) for documents in pool.values())
    click.echo(
        f"Pool contains {pool_size:,} query-document pairs in "
        f"{output / f'top-{k}-pool.json'}."
    )


if __name__ == "__main__":
    main()
