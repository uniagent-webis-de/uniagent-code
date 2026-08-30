import json

import pytest
from click.testing import CliRunner

from evaluate import (
    align_summaries,
    calculate_metrics,
    main,
    read_summaries,
    write_prototext,
)


def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_read_and_align_summaries(tmp_path):
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(
        predictions_path,
        [{"id": "2", "summary": "second"}, {"id": "1", "summary": "first"}],
    )

    predictions = read_summaries(predictions_path)
    predicted, truths = align_summaries(
        predictions, {"1": "reference one", "2": "reference two"}
    )

    assert predicted == ["first", "second"]
    assert truths == ["reference one", "reference two"]


def test_rejects_mismatched_ids():
    with pytest.raises(ValueError, match="missing prediction ids: 2"):
        align_summaries({"1": "prediction"}, {"1": "truth", "2": "truth"})


def test_identical_summaries_receive_perfect_scores():
    metrics = calculate_metrics(["a complete summary"], ["a complete summary"])

    assert metrics["BLEU"] == pytest.approx(100.0)
    assert metrics["chrF"] == pytest.approx(100.0)
    assert metrics["ROUGE-1"] == pytest.approx(1.0)
    assert metrics["ROUGE-2"] == pytest.approx(1.0)
    assert metrics["ROUGE-L"] == pytest.approx(1.0)


def test_write_prototext(tmp_path):
    output_path = write_prototext({"BLEU": 12.3456789}, tmp_path)

    assert output_path.name == "evaluation.prototext"
    assert output_path.read_text(encoding="utf-8") == (
        'measure {\n  key: "BLEU"\n  value: "12.345679"\n}\n'
    )


def test_cli_writes_results(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    truths = tmp_path / "truths.jsonl"
    results = tmp_path / "results"
    records = [{"id": "1", "summary": "the same summary"}]
    write_jsonl(predictions, records)
    write_jsonl(truths, records)

    result = CliRunner().invoke(
        main,
        [
            "--predictions",
            str(predictions),
            "--truths",
            str(truths),
            "--results",
            str(results),
        ],
    )

    assert result.exit_code == 0
    assert (results / "evaluation.prototext").is_file()
