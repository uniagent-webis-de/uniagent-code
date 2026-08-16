#!/usr/bin/env python3

import json
import os
from pathlib import Path
from urllib.parse import quote

import click
from tira.third_party_integrations import ir_datasets

from create_pool import get_pool


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def get_openai_configuration() -> dict[str, str]:
    configuration = {}
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        value = os.environ.get(name)
        if not value:
            raise ValueError(f"Missing required environment variable: {name}")
        configuration[name] = value
    return configuration


def create_umbrela_judge():
    configuration = get_openai_configuration()
    os.environ["OPEN_AI_API_KEY"] = configuration["OPENAI_API_KEY"]
    os.environ["AZURE_OPENAI_API_VERSION"] = ""
    os.environ["AZURE_OPENAI_API_BASE"] = ""
    os.environ["DEPLOYMENT_NAME"] = configuration["OPENAI_MODEL"]

    try:
        from umbrela.gpt_judge import GPTJudge
    except ImportError as error:
        raise ImportError(
            "UMBRELA is required. Install requirements-umbrela.txt with Python 3.12."
        ) from error

    return GPTJudge(
        qrel="dl19-passage",
        engine=configuration["OPENAI_MODEL"],
        few_shot_count=0,
    )


def query_text(query) -> str:
    original_query = (
        query.original_query if isinstance(query.original_query, dict) else {}
    )
    fields = [
        ("Query", query.default_text()),
        ("Description", original_query.get("description")),
        ("Narrative", original_query.get("narrative")),
    ]
    return "\n\n".join(f"{label}: {value}" for label, value in fields if value)


def build_topic_request(query, document_ids: list[str], documents) -> dict:
    candidates = []
    for document_id in document_ids:
        document = documents.get(document_id)
        if document is None:
            raise ValueError(f"Pool contains unknown document ID: {document_id}")
        candidates.append(
            {
                "docid": document_id,
                "doc": {"segment": document.default_text()},
            }
        )

    return {
        "query": {
            "qid": str(query.query_id),
            "text": query_text(query),
        },
        "candidates": candidates,
    }


def validate_response(request: dict, response: dict) -> None:
    qid = request["query"]["qid"]
    if response.get("qid") != qid:
        raise ValueError(f"Response qid does not match request qid: {qid}")

    judgments = response.get("judgments")
    if not isinstance(judgments, list):
        raise ValueError(f"Response for query {qid} has no judgments list.")

    expected_document_ids = [candidate["docid"] for candidate in request["candidates"]]
    actual_document_ids = [judgment.get("docno") for judgment in judgments]
    if actual_document_ids != expected_document_ids:
        raise ValueError(f"Response documents do not match request for query {qid}.")

    for judgment in judgments:
        label = judgment.get("judgment")
        if (
            isinstance(label, bool)
            or not isinstance(label, int)
            or label not in range(4)
        ):
            raise ValueError(
                f"Invalid judgment for query {qid}, document {judgment.get('docno')}: "
                f"{label}"
            )


def create_topic_response(request: dict, judgments: list[dict]) -> dict:
    if len(judgments) != len(request["candidates"]):
        raise ValueError(
            f"UMBRELA returned {len(judgments)} judgments for "
            f"{len(request['candidates'])} candidates."
        )

    response = {
        "qid": request["query"]["qid"],
        "judgments": [
            {
                "docno": candidate["docid"],
                "judgment": judgment.get("judgment"),
                "umbrela": judgment,
            }
            for candidate, judgment in zip(
                request["candidates"], judgments, strict=True
            )
        ],
    }
    validate_response(request, response)
    return response


def topic_path(directory: Path, qid: str) -> Path:
    return directory / f"{quote(qid, safe='')}.json"


def create_topic_judgments(
    dataset,
    pool: dict[str, list[str]],
    output_directory: Path,
    judge_factory=create_umbrela_judge,
) -> None:
    queries = {str(query.query_id): query for query in dataset.queries_iter()}
    documents = dataset.docs_store()
    requests_directory = output_directory / "requests"
    responses_directory = output_directory / "responses"
    judge = None

    for qid, document_ids in sorted(pool.items()):
        query = queries.get(qid)
        if query is None:
            raise ValueError(f"Pool contains unknown query ID: {qid}")

        request = build_topic_request(query, document_ids, documents)
        request_path = topic_path(requests_directory, qid)
        response_path = topic_path(responses_directory, qid)

        if response_path.is_file() and not request_path.is_file():
            raise ValueError(f"Response exists without request for query {qid}.")

        if request_path.is_file():
            if load_json(request_path) != request:
                raise ValueError(f"Persisted request is stale for query {qid}.")
        else:
            atomic_write_json(request_path, request)

        if response_path.is_file():
            validate_response(request, load_json(response_path))
            click.echo(f"Skip query {qid}; request and response already exist.")
            continue

        if judge is None:
            judge = judge_factory()
        response = create_topic_response(request, judge.judge(request))
        atomic_write_json(response_path, response)


def write_qrels(pool: dict[str, list[str]], output_directory: Path) -> Path:
    lines = []
    responses_directory = output_directory / "responses"

    for qid in sorted(pool):
        response_path = topic_path(responses_directory, qid)
        if not response_path.is_file():
            raise ValueError(f"Missing response for query {qid}.")
        response = load_json(response_path)
        request = {
            "query": {"qid": qid},
            "candidates": [{"docid": docno} for docno in pool[qid]],
        }
        validate_response(request, response)
        for judgment in response["judgments"]:
            lines.append(f"{qid} 0 {judgment['docno']} {judgment['judgment']}\n")

    qrels_path = output_directory / "qrels.txt"
    qrels_path.write_text("".join(lines), encoding="utf-8")
    return qrels_path


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
    help="Directory for pools, requests, responses, and qrels.txt.",
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
        loaded_dataset = ir_datasets.load(dataset)
        pool = get_pool(runs, k, output / "pools")
        create_topic_judgments(loaded_dataset, pool, output)
        qrels_path = write_qrels(pool, output)
    except (ImportError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Wrote qrels to {qrels_path}.")


if __name__ == "__main__":
    main()
