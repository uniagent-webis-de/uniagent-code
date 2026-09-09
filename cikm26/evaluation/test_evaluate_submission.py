import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from click.testing import CliRunner

from evaluate_submission import TASK_CONFIGS, _is_valid_event, analyze_run_trace, main, run_tira_evaluate


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
    def test_calls_tira_evaluate_with_predictions_truths_and_the_solving_task_config(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
            with patch("evaluate_submission.tira_evaluate") as tira_evaluate_fn:
                tira_evaluate_fn.return_value = {"accuracy": 0.8}
                measures = run_tira_evaluate(predictions, truths, "solving")

        self.assertEqual({"accuracy": 0.8}, measures)
        tira_evaluate_fn.assert_called_once_with(predictions, truths, TASK_CONFIGS["solving"])

    def test_calls_tira_evaluate_with_the_retrieval_task_config(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
            with patch("evaluate_submission.tira_evaluate") as tira_evaluate_fn:
                tira_evaluate_fn.return_value = {"nDCG@10": 0.5}
                run_tira_evaluate(predictions, truths, "retrieval")

        tira_evaluate_fn.assert_called_once_with(predictions, truths, TASK_CONFIGS["retrieval"])

    def test_raises_a_click_exception_when_the_tira_evaluator_fails(self):
        with TemporaryDirectory() as tmp:
            with patch("evaluate_submission.tira_evaluate") as tira_evaluate_fn:
                tira_evaluate_fn.side_effect = ValueError("format is invalid")
                with self.assertRaises(Exception):
                    run_tira_evaluate(Path(tmp), Path(tmp), "solving")



class MainCommandTest(unittest.TestCase):
    def test_combines_measures_with_model_and_log_line_counts(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
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
                        "--task",
                        "solving",
                        "--truths",
                        str(truths),
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        evaluate.assert_called_once_with(predictions, truths, "solving")
        report = json.loads(result.output)
        self.assertEqual(1.0, report["accuracy"])
        self.assertEqual("gpt-oss-20b", report["model"])
        self.assertEqual(1, report["valid_log_lines"])
        self.assertEqual(1, report["invalid_log_lines"])

    def test_reports_placeholder_model_and_zero_counts_without_a_run_trace_log(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            truths = Path(tmp) / "truths"
            predictions.mkdir()
            truths.mkdir()
            (predictions / "run.txt.gz").write_bytes(b"")
            with patch("evaluate_submission.run_tira_evaluate", return_value={"nDCG@10": 0.42}):
                runner = CliRunner()
                result = runner.invoke(
                    main,
                    [
                        "--predictions",
                        str(predictions),
                        "--task",
                        "retrieval",
                        "--truths",
                        str(truths),
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        report = json.loads(result.output)
        self.assertEqual(0.42, report["nDCG@10"])
        self.assertEqual("-", report["model"])
        self.assertEqual(0, report["valid_log_lines"])
        self.assertEqual(0, report["invalid_log_lines"])

    def test_forwards_a_custom_run_trace_path(self):
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
                        "--task",
                        "solving",
                        "--truths",
                        str(truths),
                        "--run-trace",
                        str(custom_trace),
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        evaluate.assert_called_once_with(predictions, truths, "solving")
        report = json.loads(result.output)
        self.assertEqual(1, report["valid_log_lines"])

    def test_downloads_truths_from_tira_when_truths_is_omitted(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp) / "predictions"
            downloaded_truths = Path(tmp) / "downloaded-truths"
            predictions.mkdir()
            downloaded_truths.mkdir()
            with (
                patch("evaluate_submission.download_truths", return_value=downloaded_truths) as download,
                patch("evaluate_submission.run_tira_evaluate", return_value={"accuracy": 0.9}) as evaluate,
            ):
                runner = CliRunner()
                result = runner.invoke(
                    main,
                    [
                        "--predictions",
                        str(predictions),
                        "--task",
                        "solving",
                        "--dataset",
                        "business-trip-spot-check-20260907-training",
                    ],
                )

        self.assertEqual(0, result.exit_code, result.output)
        download.assert_called_once_with("business-trip-spot-check-20260907-training")
        evaluate.assert_called_once_with(predictions, downloaded_truths, "solving")

    def test_fails_when_both_truths_and_dataset_are_omitted(self):
        with TemporaryDirectory() as tmp:
            predictions = Path(tmp)
            runner = CliRunner()
            result = runner.invoke(main, ["--predictions", str(predictions), "--task", "solving"])

        self.assertNotEqual(0, result.exit_code)


if __name__ == "__main__":
    unittest.main()
