#!/usr/bin/env python3

import json
from pathlib import Path

import click
import sacrebleu
from rouge_score import rouge_scorer


def read_summaries(path: Path) -> dict[str, str]:
    summaries: dict[str, str] = {}

    with path.open(encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error.msg}"
                ) from error

            identifier = record.get("id")
            summary = record.get("summary")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(
                    f"{path}:{line_number}: 'id' must be a non-empty string"
                )
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError(
                    f"{path}:{line_number}: 'summary' must be a non-empty string"
                )
            if identifier in summaries:
                raise ValueError(f"{path}:{line_number}: duplicate id '{identifier}'")

            summaries[identifier] = summary

    if not summaries:
        raise ValueError(f"{path}: no summaries found")
    return summaries


def align_summaries(
    predictions: dict[str, str], truths: dict[str, str]
) -> tuple[list[str], list[str]]:
    missing = sorted(truths.keys() - predictions.keys())
    unexpected = sorted(predictions.keys() - truths.keys())
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing prediction ids: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected prediction ids: {', '.join(unexpected)}")
        raise ValueError("; ".join(details))

    identifiers = sorted(truths)
    return (
        [predictions[identifier] for identifier in identifiers],
        [truths[identifier] for identifier in identifiers],
    )


def calculate_metrics(
    predictions: list[str], truths: list[str]
) -> dict[str, float]:
    scorer = rouge_scorer.RougeScorer(
        ["rouge1", "rouge2", "rougeL"], use_stemmer=True
    )
    rouge_scores = [
        scorer.score(truth, prediction)
        for prediction, truth in zip(predictions, truths, strict=True)
    ]

    return {
        "BLEU": sacrebleu.metrics.BLEU(effective_order=True)
        .corpus_score(predictions, [truths])
        .score,
        "chrF": sacrebleu.corpus_chrf(predictions, [truths]).score,
        "ROUGE-1": sum(score["rouge1"].fmeasure for score in rouge_scores)
        / len(rouge_scores),
        "ROUGE-2": sum(score["rouge2"].fmeasure for score in rouge_scores)
        / len(rouge_scores),
        "ROUGE-L": sum(score["rougeL"].fmeasure for score in rouge_scores)
        / len(rouge_scores),
    }


def write_prototext(metrics: dict[str, float], results_directory: Path) -> Path:
    results_directory.mkdir(parents=True, exist_ok=True)
    output_path = results_directory / "evaluation.prototext"
    blocks = [
        f'measure {{\n  key: "{name}"\n  value: "{value:.6f}"\n}}'
        for name, value in metrics.items()
    ]
    output_path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return output_path


@click.command()
@click.option(
    "--predictions",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Prediction JSONL with 'id' and 'summary' fields.",
)
@click.option(
    "--truths",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Ground-truth JSONL with 'id' and 'summary' fields.",
)
@click.option(
    "--results",
    "results_directory",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory receiving evaluation.prototext.",
)
def main(predictions: Path, truths: Path, results_directory: Path) -> None:
    try:
        prediction_summaries = read_summaries(predictions)
        truth_summaries = read_summaries(truths)
        aligned_predictions, aligned_truths = align_summaries(
            prediction_summaries, truth_summaries
        )
        metrics = calculate_metrics(aligned_predictions, aligned_truths)
        output_path = write_prototext(metrics, results_directory)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
