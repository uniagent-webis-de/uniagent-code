#!/usr/bin/env python3
"""Retrieval baseline that wraps ../retrieval-baseline-pyterrier/'s PyTerrier
BM25 pipeline with a small, self-evaluating agent (see retrieval_tools.py):

For every query, the agent
  1. retrieves candidates for the current best query text (starting with the
     query as given by the dataset),
  2. makes up to 20 of its own graded relevance judgments over those
     candidates (``judge_relevance``),
  3. scores the ranking with nDCG@10 against its own judgments
     (``compute_ndcg``),
  4. proposes a reformulated query and repeats steps 1/3 for up to
     ``--max-reformulations`` rounds, stopping early if the model reports it
     is satisfied or nDCG@10 stops improving (``reformulate_query``),
  5. finally retrieves with whichever query text scored best, and moves the
     documents it judged relevant (relevance > 0) to the top of that
     ranking, preserving the BM25 order both within the promoted documents
     and within the remaining ones.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import click
import pandas as pd
import pyterrier as pt
from tira.third_party_integrations import ir_datasets
from tqdm import tqdm

# We use the tracker to monitor resource consumption etc. of the indexing and retrieval.
from tirex_tracker import tracking
from smolagents import OpenAIModel

from event_logging import case_context, log_event, log_to_file, model_context
from retrieval_tools import QueryJudgmentStore, build_query_tools

# Same indexing configuration as ../retrieval-baseline-pyterrier/baseline.py.
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

MAX_CANDIDATES_FOR_JUDGING = 20
DEFAULT_MAX_REFORMULATIONS = 2


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


def create_index(dataset, language: str, output_dir: Path | None = None):
    if language not in RETRIEVAL_CONFIGURATION:
        raise ValueError(f"Unsupported language: {language}")

    index_directory = Path(tempfile.mkdtemp(prefix="uniagent-retrieval_"))
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="uniagent-index-metadata_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    indexer = pt.IterDictIndexer(
        str(index_directory.resolve()),
        overwrite=True,
        meta={"docno": 100},
        verbose=True,
        **RETRIEVAL_CONFIGURATION[language],
    )
    docs_to_index = (
        {"docno": str(document.doc_id), "text": document.default_text()}
        for document in tqdm(list(dataset.docs_iter()), "Index documents")
    )

    with tracking(export_file_path=output_dir / "index-ir-metadata.yml"):
        index_ref = indexer.index(docs_to_index)

    return pt.IndexFactory.of(index_ref)


def _tokenise(language: str, text: str) -> str:
    tokeniser = pt.TerrierTokeniser.java_tokeniser(RETRIEVAL_CONFIGURATION[language]["tokeniser"])
    return " ".join(tokeniser.getTokens(text))


def search(index, language: str, qid: str, query_text: str, max_results: int | None = None) -> pd.DataFrame:
    """Retrieve one query's ranking with BM25. Returns an empty frame (with
    the expected columns) if the tokenised query has no searchable terms."""
    tokenised = _tokenise(language, query_text)
    if not tokenised.strip():
        return pd.DataFrame(columns=["qid", "docno", "rank", "score"])
    topics = pd.DataFrame([{"qid": str(qid), "query": tokenised}])
    results = pt.terrier.Retriever(index, wmodel="BM25", verbose=False).transform(topics)
    if max_results is not None:
        results = results.sort_values("rank").groupby("qid").head(max_results)
    return results


def _snippet(text: str, max_characters: int = 300) -> str:
    normalised = " ".join(text.split())
    return normalised[:max_characters]


def _candidates_for_judging(results: pd.DataFrame, documents_by_id: dict[str, str]) -> list[dict[str, Any]]:
    candidates = []
    for _, row in results.sort_values("rank").head(MAX_CANDIDATES_FOR_JUDGING).iterrows():
        docno = str(row["docno"])
        text = documents_by_id.get(docno, "")
        candidates.append({"docno": docno, "snippet": _snippet(text)})
    return candidates


def reorder_with_relevant_first(results: pd.DataFrame, judgments: dict[str, int]) -> pd.DataFrame:
    """Move documents judged relevant (relevance > 0) to the top of the
    ranking, preserving the existing (BM25) relative order both among the
    promoted documents and among the remaining ones."""
    if results.empty:
        return results
    ordered = results.sort_values("rank").reset_index(drop=True)
    is_relevant = ordered["docno"].astype(str).map(lambda docno: judgments.get(docno, 0) > 0)
    reordered = pd.concat([ordered[is_relevant], ordered[~is_relevant]], ignore_index=True)
    reordered["rank"] = range(len(reordered))
    return reordered


def _run_query(
    qid: str,
    original_query: str,
    description: Optional[str],
    index,
    language: str,
    tools: dict[str, Any],
    store: QueryJudgmentStore,
    documents_by_id: dict[str, str],
    max_reformulations: int,
    progress: tqdm,
) -> pd.DataFrame:
    """Run the judge -> compute_ndcg -> reformulate loop for one query and
    return its final, reordered ranking."""
    best_query = original_query
    best_ndcg = -1.0
    best_results = pd.DataFrame(columns=["qid", "docno", "rank", "score"])
    current_query = original_query

    for iteration in range(1, max_reformulations + 2):
        results = search(index, language, qid, current_query)
        if results.empty:
            log_event("observation", input={"qid": qid, "query": current_query}, output={"hits": 0})
            break

        if iteration == 1:
            candidates = _candidates_for_judging(results, documents_by_id)
            tools["judge_relevance"](qid, current_query, candidates, description)

        ranked_docnos = results.sort_values("rank")["docno"].astype(str).tolist()
        ndcg_response = json.loads(tools["compute_ndcg"](qid, ranked_docnos))
        current_ndcg = float(ndcg_response["ndcg@10"])
        log_event(
            "observation",
            input={"qid": qid, "query": current_query},
            output={"ndcg@10": current_ndcg, "hits": len(results)},
        )

        if current_ndcg > best_ndcg:
            best_ndcg, best_query, best_results = current_ndcg, current_query, results
        progress.set_postfix_str(f"qid={qid} round={iteration} ndcg@10={current_ndcg:.3f} best={best_ndcg:.3f}")

        if iteration > max_reformulations:
            break

        reformulation = json.loads(
            tools["reformulate_query"](qid, original_query, current_query, current_ndcg, description)
        )
        if reformulation["satisfied"]:
            break
        current_query = reformulation["query"]

    judgments = store.get_judgments(qid)
    final_results = reorder_with_relevant_first(best_results, judgments)
    log_event(
        "decision",
        output={
            "qid": qid,
            "best_query": best_query,
            "best_ndcg@10": best_ndcg,
            "relevant_judged": sum(1 for grade in judgments.values() if grade > 0),
            "hits": len(final_results),
        },
    )
    progress.write(
        f"  {qid}: best_query={best_query!r} ndcg@10={best_ndcg:.3f} "
        f"relevant_judged={sum(1 for grade in judgments.values() if grade > 0)} hits={len(final_results)}"
    )
    return final_results


def run_agentic_retrieval(
    dataset,
    index,
    language: str,
    model: OpenAIModel,
    max_reformulations: int = DEFAULT_MAX_REFORMULATIONS,
) -> pd.DataFrame:
    documents_by_id = {
        str(document.doc_id): document.default_text() for document in dataset.docs_iter()
    }
    store = QueryJudgmentStore()
    tools = build_query_tools(model, store)

    runs = []
    queries = list(dataset.queries_iter())
    click.echo(f"Running agentic retrieval for {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}...")
    progress = tqdm(queries, desc="Agentic retrieval", unit="query")
    for query in progress:
        qid = str(query.query_id)
        original_query = query.default_text()
        description = None
        if isinstance(query.original_query, dict):
            description = query.original_query.get("description")
        progress.set_postfix_str(f"qid={qid}")

        with case_context(qid):
            # A single query's judging/reformulation loop must not abort the
            # whole run (e.g. every judgment the model returned turned out to
            # be unusable, or any other unexpected tool/model error): log the
            # failure and fall back to the query's plain BM25 ranking (no
            # judged reordering) instead, so every other query still gets
            # processed and this one still contributes a ranking to run.txt.gz.
            try:
                final_results = _run_query(
                    qid,
                    original_query,
                    description,
                    index,
                    language,
                    tools,
                    store,
                    documents_by_id,
                    max_reformulations,
                    progress,
                )
            except Exception as error:
                log_event(
                    "error",
                    input={"qid": qid, "query": original_query},
                    output=None,
                    status="error",
                    error=str(error),
                )
                final_results = search(index, language, qid, original_query)
                log_event(
                    "decision",
                    output={
                        "qid": qid,
                        "best_query": original_query,
                        "best_ndcg@10": None,
                        "relevant_judged": 0,
                        "hits": len(final_results),
                    },
                    status="error",
                    error=str(error),
                )
                progress.write(f"  {qid}: FAILED ({error}); falling back to plain BM25 ranking.")
        runs.append(final_results)

    if not runs:
        return pd.DataFrame(columns=["qid", "docno", "rank", "score"])
    return pd.concat(runs, ignore_index=True)


def required_environment() -> tuple[str, str, str]:
    values = []
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"Required environment variable {name} is not set.")
        values.append(value)
    return values[0], values[1], values[2]


@click.command()
@click.option(
    "--dataset",
    required=True,
    help="The TIRA dataset ID or local dataset directory.",
)
@click.option(
    "--max-reformulations",
    default=DEFAULT_MAX_REFORMULATIONS,
    show_default=True,
    help="Maximum number of query-reformulation rounds per query.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, file_okay=False),
    help="The output directory.",
)
def main(dataset: str, output: Path, max_reformulations: int) -> None:
    if max_reformulations < 0:
        raise click.BadParameter("--max-reformulations must not be negative.")

    ir_dataset = ir_datasets.load(dataset)

    try:
        language = detect_query_language(ir_dataset)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    output.mkdir(parents=True, exist_ok=True)
    (output / "language.txt").write_text(f"{language}\n", encoding="utf-8")
    click.echo(f"Detected query language: {language}")

    api_base, api_key, model_id = required_environment()
    model = OpenAIModel(model_id=model_id, api_base=api_base, api_key=api_key, temperature=0)

    index = create_index(ir_dataset, language, output)

    run_trace_log = output / "run-trace.jsonl.log.gz"
    with log_to_file(run_trace_log), model_context(model_id):
        with tracking(export_file_path=output / "retrieval-ir-metadata.yml"):
            run = run_agentic_retrieval(ir_dataset, index, language, model, max_reformulations)
    pt.io.write_results(run, str(output / "run.txt.gz"))
    click.echo(f"Wrote {len(run)} run row(s) and event trace to {run_trace_log}.")


if __name__ == "__main__":
    main()
