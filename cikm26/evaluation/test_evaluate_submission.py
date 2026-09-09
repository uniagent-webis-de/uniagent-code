import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from click.testing import CliRunner

from evaluate_submission import _is_valid_event, analyze_run_trace, main, run_tira_evaluate


def _write_run_trace(directory: Path, lines: list[str], filename: str = "run-trace.jsonl.log.gz") -> Path:
    path = directory / filename
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
    return path


def _valid_event(**overrides) -> dict:
    event = {
        "case_id": "dienstreiseantrag-01",
        "event_id": "evt-0001",
        "parent_event_id": None,
        "timestamp": "2026-09-09T12:00:00.000+00:00",
        "event_type": "tool_call",
        "model": "gpt-oss-20b",
        "tool": "read_pdf",
        "input": {"filename": "a.pdf"},
        "output": "text",
        "status": "ok",
        "error": None,
    }
    event.update(overrides)
    return event


class IsValidEventTest(unittest.TestCase):
    def test_accepts_a_fully_populated_event(self):
        self.assertTrue(_is_valid_event(_valid_event()))

    def test_accepts_the_deterministic_placeholder_model(self):
        self.assertTrue(_is_valid_event(_valid_event(model="-")))

    def test_rejects_a_non_object(self):
        self.assertFalse(_is_valid_event("not an object"))
        self.assertFalse(_is_valid_event(["also", "not"]))

    def test_rejects_missing_required_fields(self):
        event = _valid_event()
        del event["parent_event_id"]
        self.assertFalse(_is_valid_event(event))

    def test_rejects_a_missing_or_empty_model(self):
        self.assertFalse(_is_valid_event(_valid_event(model=None)))
        self.assertFalse(_is_valid_event(_valid_event(model="")))
        self.assertFalse(_is_valid_event(_valid_event(model="   ")))

    def test_rejects_an_invalid_status(self):
        self.assertFalse(_is_valid_event(_valid_event(status="pending")))


class AnalyzeRunTraceTest(unittest.TestCase):
    def test_returns_placeholder_and_zero_counts_when_the_file_is_missing(self):
        with TemporaryDirectory() as tmp:
            model, valid, invalid = analyze_run_trace(Path(tmp) / "run-trace.jsonl.log.gz")
        self.assertEqual("-", model)
        self.assertEqual(0, valid)
        self.assertEqual(0, invalid)

    def test_counts_valid_and_invalid_lines_and_reports_the_model(self):
        with TemporaryDirectory() as tmp:
            path = _write_run_trace(
                Path(tmp),
                [
                    json.dumps(_valid_event(event_id="evt-0001")),
                    "not even json",
                    json.dumps({"case_id": "x"}),  # missing required fields
                    json.dumps(_valid_event(event_id="evt-0002", event_type="decision")),
                ],
            )
            model, valid, invalid = analyze_run_trace(path)
        self.assertEqual("gpt-oss-20b", model)
        self.assertEqual(2, valid)
        self.assertEqual(2, invalid)

    def test_reports_placeholder_model_when_every_valid_event_uses_it(self):
        with TemporaryDirectory() as tmp:
            path = _write_run_trace(Path(tmp), [json.dumps(_valid_event(model="-"))])
            model, valid, invalid = analyze_run_trace(path)
        self.assertEqual("-", model)
        self.assertEqual(1, valid)
        self.assertEqual(0, invalid)

    def test_ignores_blank_lines(self):
        with TemporaryDirectory() as tmp:
            path = _write_run_trace(Path(tmp), ["", "   ", json.dumps(_valid_event())])
            model, valid, invalid = analyze_run_trace(path)
        self.assertEqual("gpt-oss-20b", model)
        self.assertEqual(1, valid)
        self.assertEqual(0, invalid)


class RunTiraEvaluateTest(unittest.TestCase):
    def test_calls_client_evaluate_with_predictions_dataset_and_truths(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp)
            with patch("evaluate_submission.RestClient") as rest_client_cls:
                rest_client_cls.return_value.evaluate.return_value = {"accuracy": 0.8}
                measures = run_tira_evaluate(predictions, "business-trip-spot-check-20260907-training", None)

        self.assertEqual({"accuracy": 0.8}, measures)
        rest_client_cls.return_value.evaluate.assert_called_once_with(
            predictions, None, "business-trip-spot-check-20260907-training"
        )

    def test_forwards_truths_when_given(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
            with patch("evaluate_submission.RestClient") as rest_client_cls:
                rest_client_cls.return_value.evaluate.return_value = {"nDCG@10": 0.5}
                run_tira_evaluate(predictions, "retrieval-de-spot-check-20260816-training", truths)

        rest_client_cls.return_value.evaluate.assert_called_once_with(
            predictions, truths, "retrieval-de-spot-check-20260816-training"
        )

    def test_raises_a_click_exception_when_the_tira_client_fails(self):
        with TemporaryDirectory() as tmp:
            with patch("evaluate_submission.RestClient") as rest_client_cls:
                rest_client_cls.return_value.evaluate.side_effect = ValueError("dataset not found")
                with self.assertRaises(Exception):
                    run_tira_evaluate(Path(tmp), "unknown-dataset", None)



class MainCommandTest(unittest.TestCase):
    def test_combines_measures_with_model_and_log_line_counts(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp)
            (predictions / "predictions.jsonl").write_text(
                json.dumps({"antrag": "dienstreiseantrag-01", "result": "abgelehnt"}) + "\n"
            )
            _write_run_trace(
                predictions,
                [json.dumps(_valid_event()), "broken"],
            )
            with patch("evaluate_submission.run_tira_evaluate", return_value={"accuracy": 1.0}) as evaluate:
                runner = CliRunner()
                result = runner.invoke(
                    main,
                    [
                        "--predictions",
                        str(predictions),
                        "--dataset",
                        "business-trip-spot-check-20260907-training",
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        evaluate.assert_called_once_with(predictions, "business-trip-spot-check-20260907-training", None)
        report = json.loads(result.output)
        self.assertEqual(1.0, report["accuracy"])
        self.assertEqual("gpt-oss-20b", report["model"])
        self.assertEqual(1, report["valid_log_lines"])
        self.assertEqual(1, report["invalid_log_lines"])

    def test_reports_placeholder_model_and_zero_counts_without_a_run_trace_log(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp)
            (predictions / "run.txt.gz").write_bytes(b"")
            with patch("evaluate_submission.run_tira_evaluate", return_value={"nDCG@10": 0.42}):
                runner = CliRunner()
                result = runner.invoke(
                    main,
                    [
                        "--predictions",
                        str(predictions),
                        "--dataset",
                        "retrieval-de-spot-check-20260816-training",
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        report = json.loads(result.output)
        self.assertEqual(0.42, report["nDCG@10"])
        self.assertEqual("-", report["model"])
        self.assertEqual(0, report["valid_log_lines"])
        self.assertEqual(0, report["invalid_log_lines"])

    def test_forwards_truths_and_a_custom_run_trace_path(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
            custom_trace = predictions / "custom-trace.jsonl.log.gz"
            _write_run_trace(predictions, [json.dumps(_valid_event())], filename="custom-trace.jsonl.log.gz")

            with patch("evaluate_submission.run_tira_evaluate", return_value={"accuracy": 0.6}) as evaluate:
                runner = CliRunner()
                result = runner.invoke(
                    main,
                    [
                        "--predictions",
                        str(predictions),
                        "--dataset",
                        "business-trip-spot-check-20260907-training",
                        "--truths",
                        str(truths),
                        "--run-trace",
                        str(custom_trace),
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        evaluate.assert_called_once_with(predictions, "business-trip-spot-check-20260907-training", truths)
        report = json.loads(result.output)
        self.assertEqual(1, report["valid_log_lines"])


if __name__ == "__main__":
    unittest.main()
