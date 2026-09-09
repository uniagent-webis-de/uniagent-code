#!/usr/bin/env python3
"""Dockerized evaluation for UniAgent'26 cikm26 submissions.

Uses the `tira` Python package's `Client.evaluate()`
(https://github.com/tira-io/tira, the same method `tira-cli evaluate` calls
internally) to compute the task-specific measure(s) for a submission's
predictions, compatible with both kinds of spot-check datasets in this
repository:

- Task 2 "Solving" datasets such as `../datasets/business-trip-spot-check/`
  (`predictions.jsonl`, evaluated by `accuracy`, see that dataset's README's
  `tira_configs.evaluator`), and
- Task 1 "Retrieval" datasets such as `../datasets/retrieval-de-spot-check/`
  (`run.txt.gz`, evaluated by `nDCG@10`, see that dataset's README's
  `tira_configs.evaluator`).

`Client.evaluate()` itself decides which measure(s) to compute from the
dataset's own trusted-evaluator configuration on TIRA, so this script has no
task-specific logic beyond that single call.

In addition to the measure(s) `Client.evaluate()` reports, this script always
reports the LLM model used for the run (per the required `model` field in
`../event-logging-contract/README.md`, or `-` for model-free submissions such
as `business-trip-always-rejected` or the retrieval baselines) and how many
lines of the submission's `run-trace.jsonl.log.gz` are contract-valid versus
invalid, so a submission's compliance with the event-logging contract is
visible alongside its task measure(s).
"""
import gzip
import json
from pathlib import Path
from typing import Any, Optional

import click
from tira.rest_api_client import Client as RestClient

RUN_TRACE_FILENAME = "run-trace.jsonl.log.gz"

# Every event must have exactly these fields per the event-logging contract
# (../event-logging-contract/README.md, requirement 3); values may be null,
# but the keys themselves must be present.
REQUIRED_EVENT_FIELDS = (
    "case_id",
    "event_id",
    "parent_event_id",
    "timestamp",
    "event_type",
    "model",
    "tool",
    "input",
    "output",
    "status",
    "error",
)


def _is_valid_event(entry: Any) -> bool:
    """Check one decoded JSON line against the event-logging contract.

    Requires an object with all `REQUIRED_EVENT_FIELDS` present, a non-empty
    `model` (required on every event, never null/omitted per the contract),
    and `status` being one of the two values the contract allows.
    """
    if not isinstance(entry, dict):
        return False
    if not all(field in entry for field in REQUIRED_EVENT_FIELDS):
        return False
    if not isinstance(entry.get("model"), str) or not entry["model"].strip():
        return False
    if entry.get("status") not in {"ok", "error"}:
        return False
    return True


def analyze_run_trace(path: Path) -> tuple[str, int, int]:
    """Return `(model, valid_line_count, invalid_line_count)` for a run-trace log.

    `model` is the first non-placeholder (i.e. not `"-"`) model identifier
    found across all valid events, or `"-"` if the log has none (e.g. a
    purely deterministic submission). A missing file is treated as zero
    valid and zero invalid lines rather than an error, since logging can
    legitimately be skipped entirely for submissions with no tools and no
    model calls (contract requirement 1).
    """
    if not path.is_file():
        return "-", 0, 0

    model = "-"
    valid = 0
    invalid = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if not _is_valid_event(entry):
                invalid += 1
                continue
            valid += 1
            if model == "-":
                candidate = entry.get("model")
                if candidate and candidate != "-":
                    model = candidate
    return model, valid, invalid


def run_tira_evaluate(predictions: Path, dataset: str, truths: Optional[Path]) -> dict[str, Any]:
    """Compute the measures for `predictions` via `tira`'s `Client.evaluate()`.

    This is the one place that talks to TIRA: `Client.evaluate()` (the same
    method the `tira-cli evaluate` subcommand calls internally, see
    `RestClient.evaluate()` in tira's `tira_client.py`) looks up `dataset`'s
    trusted-evaluator configuration on TIRA (e.g.
    `business-trip-spot-check-20260907-training` or
    `retrieval-de-spot-check-20260816-training`, see the "Submit to TIRA"
    sections of the baselines' READMEs under `../baselines/`) and evaluates
    `predictions` locally against either `truths` (if given) or the
    dataset's own published truths.
    """
    try:
        return RestClient().evaluate(predictions, truths, dataset)
    except Exception as error:
        raise click.ClickException(f"tira evaluation failed: {error}") from error


@click.command()
@click.option(
    "--predictions",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory with the submission's output (predictions.jsonl or run.txt.gz), "
    f"and optionally its {RUN_TRACE_FILENAME} event trace.",
)
@click.option(
    "--dataset",
    required=True,
    help="The TIRA dataset ID to evaluate against, e.g. "
    "business-trip-spot-check-20260907-training or retrieval-de-spot-check-20260816-training.",
)
@click.option(
    "--truths",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Optional local truths directory; tira downloads the dataset's published truths if omitted.",
)
@click.option(
    "--run-trace",
    "run_trace_path",
    default=None,
    type=click.Path(path_type=Path),
    help=f"Override the run-trace log path (default: <predictions>/{RUN_TRACE_FILENAME}).",
)
def main(
    predictions: Path,
    dataset: str,
    truths: Optional[Path],
    run_trace_path: Optional[Path],
) -> None:
    """Evaluate a cikm26 submission with tira's `Client.evaluate()`, plus event-log stats.

    Works for both Task 2 "Solving" datasets (e.g. business-trip-spot-check,
    evaluated by accuracy) and Task 1 "Retrieval" datasets (e.g.
    retrieval-de-spot-check, evaluated by nDCG@10) -- see
    ../datasets/business-trip-spot-check/README.md and
    ../datasets/retrieval-de-spot-check/README.md.
    """
    measures = run_tira_evaluate(predictions, dataset, truths)

    trace_path = run_trace_path if run_trace_path is not None else predictions / RUN_TRACE_FILENAME
    model, valid_lines, invalid_lines = analyze_run_trace(trace_path)

    report = dict(measures)
    report["model"] = model
    report["valid_log_lines"] = valid_lines
    report["invalid_log_lines"] = invalid_lines

    click.echo(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
