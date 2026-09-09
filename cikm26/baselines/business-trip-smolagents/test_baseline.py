import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from business_trip_tools import (
    CheckFactsTool,
    ListCaseDocumentsTool,
    LookupPolicyTool,
    ReadPdfTool,
    SearchCaseTool,
)
from event_logging import case_context, log_event, log_tool_calls, log_to_file, model_context, reset_state
from predict import build_case_evidence, decide_case, input_cases, parse_decision


DATASET = (
    Path(__file__).parents[2] / "datasets" / "business-trip-spot-check" / "inputs"
).resolve()


class BaselineTest(unittest.TestCase):
    def test_lists_all_cases(self):
        self.assertEqual(
            input_cases(DATASET),
            [f"dienstreiseantrag-0{index}" for index in range(1, 6)],
        )

    def test_lists_and_reads_case_documents(self):
        case_id = "dienstreiseantrag-03"
        listed = json.loads(ListCaseDocumentsTool(DATASET, case_id)(case_id))
        self.assertEqual(3, len(listed))
        text = ReadPdfTool(DATASET, case_id)(case_id, "antrag-dienstreisegenehmigung.pdf")
        self.assertIn("Lyon, FRANKREICH", text)

    def test_rejects_cross_case_access(self):
        tool = ListCaseDocumentsTool(DATASET, "dienstreiseantrag-03")
        with self.assertRaises(ValueError):
            tool("dienstreiseantrag-04")

    def test_searches_with_citations(self):
        case_id = "dienstreiseantrag-05"
        matches = json.loads(SearchCaseTool(DATASET, case_id)(case_id, "Doppelfinanzierung", 5))
        self.assertTrue(matches)
        self.assertEqual("email-stipendienzusage.pdf", matches[0]["document"])

    def test_policy_lookup(self):
        result = json.loads(LookupPolicyTool()("Doppelfinanzierung Stipendium"))
        self.assertIn("double_funding", result["policies"])

    def test_deterministic_fact_checks(self):
        tool = CheckFactsTool()
        dates = json.loads(
            tool(
                {
                    "kind": "compare_dates",
                    "comparisons": [
                        {
                            "name": "application_before_trip",
                            "left": "20.10.2026",
                            "operator": "<",
                            "right": "14.10.2026",
                        }
                    ],
                }
            )
        )
        self.assertFalse(dates["results"][0]["passed"])

        overlap = json.loads(
            tool(
                {
                    "kind": "overlap",
                    "left": ["Flug", "Unterkunft"],
                    "right": ["Konferenz", "Flug"],
                }
            )
        )
        self.assertEqual(["flug"], overlap["overlap"])

    def test_parses_strict_decision(self):
        answer = json.dumps(
            {
                "antrag": "dienstreiseantrag-01",
                "result": "abgelehnt",
                "begruendung": "Der Antrag wurde nach Reisebeginn gestellt.",
            }
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_parses_json_embedded_in_short_explanation(self):
        answer = (
            "Ergebnis:\n"
            '{"antrag":"dienstreiseantrag-01","result":"abgelehnt",'
            '"begruendung":"Der Antrag wurde nach Reisebeginn gestellt."}'
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_does_not_accept_malformed_decision(self):
        with self.assertRaises(ValueError):
            parse_decision("abgelehnt", "dienstreiseantrag-01")

    def test_builds_complete_case_evidence(self):
        evidence = build_case_evidence(DATASET, "dienstreiseantrag-01")
        self.assertIn("antrag-dienstreisegenehmigung.pdf", evidence["documents"])
        self.assertTrue(evidence["document_completeness_check"]["complete"])
        self.assertIn("advance_approval", evidence["policies"]["policies"])

    def test_decides_from_preloaded_evidence_without_agent_protocol(self):
        class FakeModel:
            def __init__(self):
                self.messages = None

            def generate(self, messages, **_kwargs):
                self.messages = messages
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "antrag": "dienstreiseantrag-01",
                            "result": "abgelehnt",
                            "begruendung": "Der Antrag wurde nach der Reise gestellt.",
                        }
                    ),
                    raw=None,
                )

        import contextlib
        import io

        model = FakeModel()
        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case(DATASET, "dienstreiseantrag-01", model)
        self.assertEqual("abgelehnt", decision["result"])
        self.assertIn("bahn-rechnung-kassel-leipzig.pdf", model.messages[1]["content"])

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        event_types = [entry["event_type"] for entry in entries]
        self.assertIn("model_call", event_types)
        self.assertEqual("decision", event_types[-1])
        for entry in entries:
            self.assertEqual("dienstreiseantrag-01", entry["case_id"])
            self.assertEqual("gpt-oss-20b", entry["model"])
            self.assertEqual("ok", entry["status"])
        self.assertEqual(decision, entries[-1]["output"])
        # Chain is unbroken: every event but the first has a parent among
        # the previously logged events.
        self.assertIsNone(entries[0]["parent_event_id"])
        logged_ids = {entry["event_id"] for entry in entries}
        for entry in entries[1:]:
            self.assertIn(entry["parent_event_id"], logged_ids)


class EventLoggingTest(unittest.TestCase):
    def test_logs_one_json_object_per_call_with_the_documented_fields(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message * 2

        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            with case_context("dienstreiseantrag-07"), model_context("gpt-oss-20b"):
                result = tool.forward(message="hi")

        self.assertEqual("hihi", result)
        entry = self._single_json_line(output)
        self.assertEqual(
            {
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
            },
            set(entry),
        )
        self.assertEqual("dienstreiseantrag-07", entry["case_id"])
        self.assertEqual("tool_call", entry["event_type"])
        self.assertEqual("gpt-oss-20b", entry["model"])
        self.assertEqual("echo", entry["tool"])
        self.assertEqual({"message": "hi"}, entry["input"])
        self.assertEqual("hihi", entry["output"])
        self.assertEqual("ok", entry["status"])
        self.assertIsNone(entry["error"])

    def test_logs_errors_without_swallowing_them(self):
        class FailingTool:
            name = "fails"

            def forward(self) -> str:
                raise ValueError("boom")

        tool = log_tool_calls(FailingTool())
        with self._capture_stdout() as output:
            with self.assertRaises(ValueError):
                tool.forward()

        entry = self._single_json_line(output)
        self.assertEqual("error", entry["status"])
        self.assertEqual("boom", entry["error"])
        self.assertIsNone(entry["output"])

    def test_defaults_to_placeholder_context_and_model_outside_any_context(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            tool.forward(message="hi")

        entry = self._single_json_line(output)
        self.assertEqual("-", entry["case_id"])
        self.assertEqual("-", entry["model"])

    def test_truncates_long_string_inputs_and_outputs(self):
        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        long_text = "x" * 500
        tool = log_tool_calls(EchoTool())
        with self._capture_stdout() as output:
            tool.forward(message=long_text)

        entry = self._single_json_line(output)
        self.assertLessEqual(len(entry["input"]["message"]), 200)
        self.assertTrue(entry["input"]["message"].endswith("…"))
        self.assertLessEqual(len(entry["output"]), 200)

    def test_keeps_small_structured_inputs_as_native_json(self):
        class ChecksTool:
            name = "check_facts"

            def forward(self, facts: dict) -> str:
                return json.dumps(facts)

        tool = log_tool_calls(ChecksTool())
        with self._capture_stdout() as output:
            tool.forward(facts={"kind": "overlap", "left": ["a"], "right": ["a"]})

        entry = self._single_json_line(output)
        self.assertEqual(
            {"kind": "overlap", "left": ["a"], "right": ["a"]}, entry["input"]["facts"]
        )

    def test_log_to_file_writes_gzip_compressed_jsonl_lines_instead_of_stdout(self):
        import gzip
        import tempfile

        class EchoTool:
            name = "echo"

            def forward(self, message: str) -> str:
                return message

        tool = log_tool_calls(EchoTool())
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run_trace.jsonl.gz"
            with self._capture_stdout() as output:
                with log_to_file(log_path):
                    tool.forward(message="hi")
                    tool.forward(message="ho")
                tool.forward(message="outside")

            stdout_lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
            self.assertEqual(["outside"], [line["input"]["message"] for line in stdout_lines])
            with gzip.open(log_path, "rt", encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(["hi", "ho"], [line["input"]["message"] for line in lines])

    @staticmethod
    def _capture_stdout():
        import contextlib
        import io

        return contextlib.redirect_stdout(io.StringIO())

    def _single_json_line(self, output) -> dict:
        lines = [line for line in output.getvalue().splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        return json.loads(lines[0])


class CaseEventLoggingIntegrationTest(unittest.TestCase):
    def test_build_case_evidence_logs_one_jsonl_line_per_tool_call_with_a_causal_chain(self):
        import contextlib
        import io

        reset_state()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                build_case_evidence(DATASET, "dienstreiseantrag-01")

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        self.assertTrue(entries)
        for entry in entries:
            self.assertEqual("dienstreiseantrag-01", entry["case_id"])
            self.assertEqual("ok", entry["status"])
            self.assertEqual("tool_call", entry["event_type"])
            self.assertEqual("gpt-oss-20b", entry["model"])
        logged_tools = {entry["tool"] for entry in entries}
        self.assertEqual(
            {"list_case_documents", "read_pdf", "search_case", "lookup_policy", "check_facts"},
            logged_tools,
        )
        self.assertIsNone(entries[0]["parent_event_id"])
        logged_ids = {entry["event_id"] for entry in entries}
        for entry in entries[1:]:
            self.assertIn(entry["parent_event_id"], logged_ids)


if __name__ == "__main__":
    unittest.main()
