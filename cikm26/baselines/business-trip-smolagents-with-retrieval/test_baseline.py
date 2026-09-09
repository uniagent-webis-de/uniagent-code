import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from predict import (
    build_case_evidence,
    build_retrieval_query,
    decide_case,
    gather_case_knowledge,
    identify_key_aspects,
    input_cases,
    parse_aspect_response,
    parse_decision,
)
from retrieval_tools import (
    build_retrieval_tools,
    discover_corpora,
    document_text,
    infer_language,
    read_documents,
)
from event_logging import case_context, log_event, log_tool_calls, log_to_file, model_context, reset_state


DATASET = (
    Path(__file__).parents[2] / "datasets" / "business-trip-spot-check" / "inputs"
).resolve()


class InputScanningTest(unittest.TestCase):
    def test_lists_all_cases_and_excludes_retrieval_corpora(self):
        self.assertEqual(
            input_cases(DATASET),
            [f"dienstreiseantrag-0{index}" for index in range(1, 6)],
        )


class CorpusDiscoveryTest(unittest.TestCase):
    def test_discovers_every_shipped_corpus(self):
        corpora = discover_corpora(DATASET)
        self.assertEqual(
            {"hessian-law-de", "university-kassel-public-de", "university-kassel-public-en"},
            set(corpora),
        )

    def test_returns_empty_mapping_without_retrieval_corpora_directory(self):
        self.assertEqual({}, discover_corpora(DATASET / "dienstreiseantrag-01"))

    def test_reads_documents_and_infers_language_by_folder_suffix(self):
        corpora = discover_corpora(DATASET)
        documents = read_documents(corpora["hessian-law-de"])
        self.assertGreater(len(documents), 0)
        self.assertEqual("de", infer_language("hessian-law-de", documents[0]))
        self.assertEqual("en", infer_language("university-kassel-public-en", documents[0]))

    def test_document_text_prefers_content_field(self):
        self.assertEqual("hello", document_text({"content": "hello", "text": "other"}))

    def test_document_text_rejects_empty_documents(self):
        with self.assertRaises(ValueError):
            document_text({"doc_id": "x", "content": "", "text": ""})


class RetrievalToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = {tool.name: tool for tool in build_retrieval_tools(DATASET)}

    def test_builds_one_tool_per_corpus(self):
        self.assertEqual(
            {
                "retrieve_hessian_law_de",
                "retrieve_university_kassel_public_de",
                "retrieve_university_kassel_public_en",
            },
            set(self.tools),
        )

    def test_retrieves_ranked_cited_hits(self):
        hits = json.loads(
            self.tools["retrieve_hessian_law_de"](query="Reisekosten Erstattung", max_results=3)
        )
        self.assertLessEqual(len(hits), 3)
        if hits:
            hit = hits[0]
            self.assertEqual("hessian-law-de", hit["corpus"])
            self.assertIn("doc_id", hit)
            self.assertIn("snippet", hit)

    def test_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            self.tools["retrieve_hessian_law_de"](query="   ")

    def test_rejects_out_of_range_max_results(self):
        with self.assertRaises(ValueError):
            self.tools["retrieve_hessian_law_de"](query="Reisekosten", max_results=21)


class RetrievalQueryTest(unittest.TestCase):
    def test_combines_application_text_with_fixed_keywords(self):
        evidence = {"documents": {"antrag-dienstreisegenehmigung.pdf": "Lyon, FRANKREICH"}}
        query = build_retrieval_query(evidence)
        self.assertIn("Lyon, FRANKREICH", query)
        self.assertIn("Doppelfinanzierung", query)

    def test_gathers_and_ranks_knowledge_across_corpora(self):
        class FakeTool:
            def __init__(self, name, hits):
                self.name = name
                self._hits = hits

            def __call__(self, query, max_results):
                return json.dumps(self._hits)

        tools = [
            FakeTool("retrieve_a", [{"corpus": "a", "score": 1.0}]),
            FakeTool("retrieve_b", [{"corpus": "b", "score": 5.0}]),
        ]
        knowledge = gather_case_knowledge(tools, "query")
        self.assertEqual(["b", "a"], [hit["corpus"] for hit in knowledge])


class DecisionPipelineTest(unittest.TestCase):
    def test_builds_complete_case_evidence(self):
        evidence = build_case_evidence(DATASET, "dienstreiseantrag-01")
        self.assertIn("antrag-dienstreisegenehmigung.pdf", evidence["documents"])
        self.assertTrue(evidence["document_completeness_check"]["complete"])

    def test_parses_strict_decision(self):
        answer = json.dumps(
            {
                "antrag": "dienstreiseantrag-01",
                "result": "abgelehnt",
                "begruendung": "Der Antrag wurde nach Reisebeginn gestellt.",
            }
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_does_not_accept_malformed_decision(self):
        with self.assertRaises(ValueError):
            parse_decision("abgelehnt", "dienstreiseantrag-01")

    def test_decides_from_preloaded_evidence_and_knowledge(self):
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

        evidence = build_case_evidence(DATASET, "dienstreiseantrag-01")
        knowledge = [{"corpus": "hessian-law-de", "doc_id": "x", "score": 1.0}]
        aspects = [{"aspect": "Frist", "finding": "...", "corpus": "hessian-law-de", "doc_id": "x"}]
        model = FakeModel()
        import contextlib
        import io

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                decision = decide_case("dienstreiseantrag-01", evidence, knowledge, aspects, model)
        self.assertEqual("abgelehnt", decision["result"])
        self.assertIn("external_knowledge", model.messages[1]["content"])
        self.assertIn("key_aspects", model.messages[1]["content"])
        self.assertIn("bahn-rechnung-kassel-leipzig.pdf", model.messages[1]["content"])

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        self.assertEqual(["model_call", "decision"], [entry["event_type"] for entry in entries])
        for entry in entries:
            self.assertEqual("dienstreiseantrag-01", entry["case_id"])
            self.assertEqual("gpt-oss-20b", entry["model"])
            self.assertEqual("ok", entry["status"])
        self.assertEqual(entries[0]["event_id"], entries[1]["parent_event_id"])
        self.assertEqual(decision, entries[1]["output"])


class AspectAnalysisTest(unittest.TestCase):
    def test_parses_valid_aspect_response(self):
        answer = json.dumps(
            {
                "aspects": [
                    {
                        "aspect": "Frist",
                        "finding": "Antrag muss vor Reisebeginn gestellt werden.",
                        "corpus": "hessian-law-de",
                        "doc_id": "x",
                    }
                ],
                "sufficient": True,
                "follow_up_query": "",
            }
        )
        parsed = parse_aspect_response(answer)
        self.assertEqual(1, len(parsed["aspects"]))
        self.assertTrue(parsed["sufficient"])
        self.assertEqual("", parsed["follow_up_query"])

    def test_rejects_response_without_aspects_list(self):
        with self.assertRaises(ValueError):
            parse_aspect_response(json.dumps({"sufficient": True}))

    def test_rejects_aspect_without_title(self):
        with self.assertRaises(ValueError):
            parse_aspect_response(json.dumps({"aspects": [{"finding": "..."}], "sufficient": True}))

    def test_stops_as_soon_as_model_reports_sufficient(self):
        class FakeTool:
            def __init__(self, name):
                self.name = name
                self.calls = 0

            def __call__(self, query, max_results):
                self.calls += 1
                return json.dumps([{"corpus": "hessian-law-de", "doc_id": "x", "score": 1.0}])

        class FakeModel:
            def __init__(self):
                self.calls = 0

            def generate(self, messages, **_kwargs):
                self.calls += 1
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "aspects": [
                                {
                                    "aspect": "Frist",
                                    "finding": "rechtzeitig gestellt",
                                    "corpus": "hessian-law-de",
                                    "doc_id": "x",
                                }
                            ],
                            "sufficient": True,
                            "follow_up_query": "",
                        }
                    ),
                    raw=None,
                )

        tool = FakeTool("retrieve_hessian_law_de")
        evidence = {"case_id": "dienstreiseantrag-01", "documents": {}}
        knowledge, aspects, iterations = identify_key_aspects(
            "dienstreiseantrag-01", evidence, [tool], FakeModel()
        )
        self.assertEqual(1, iterations)
        self.assertEqual(1, tool.calls)
        self.assertEqual(1, len(knowledge))
        self.assertEqual(1, len(aspects))

    def test_logs_a_model_call_event_per_retrieval_iteration(self):
        import contextlib
        import io

        class FakeTool:
            def __init__(self, name):
                self.name = name

            def __call__(self, query, max_results):
                return json.dumps([{"corpus": "hessian-law-de", "doc_id": "x", "score": 1.0}])

        class FakeModel:
            def generate(self, messages, **_kwargs):
                return SimpleNamespace(
                    content=json.dumps(
                        {"aspects": [], "sufficient": True, "follow_up_query": ""}
                    ),
                    raw=None,
                )

        tool = FakeTool("retrieve_hessian_law_de")
        evidence = {"case_id": "dienstreiseantrag-01", "documents": {}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with case_context("dienstreiseantrag-01"), model_context("gpt-oss-20b"):
                identify_key_aspects("dienstreiseantrag-01", evidence, [tool], FakeModel())

        entries = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        model_calls = [entry for entry in entries if entry["event_type"] == "model_call"]
        self.assertEqual(1, len(model_calls))
        self.assertEqual("gpt-oss-20b", model_calls[0]["model"])
        self.assertEqual("ok", model_calls[0]["status"])
        self.assertIn("prompt", model_calls[0]["input"])

    def test_runs_a_follow_up_iteration_when_model_reports_insufficient(self):
        class FakeTool:
            def __init__(self, name):
                self.name = name
                self.queries = []

            def __call__(self, query, max_results):
                self.queries.append(query)
                doc_id = "x" if len(self.queries) == 1 else "y"
                return json.dumps([{"corpus": "hessian-law-de", "doc_id": doc_id, "score": 1.0}])

        class FakeModel:
            def __init__(self):
                self.calls = 0

            def generate(self, messages, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    content = json.dumps(
                        {
                            "aspects": [],
                            "sufficient": False,
                            "follow_up_query": "A1-Bescheinigung Ausland",
                        }
                    )
                else:
                    content = json.dumps(
                        {
                            "aspects": [
                                {
                                    "aspect": "A1-Bescheinigung",
                                    "finding": "bei Auslandsreisen erforderlich",
                                    "corpus": "hessian-law-de",
                                    "doc_id": "y",
                                }
                            ],
                            "sufficient": True,
                            "follow_up_query": "",
                        }
                    )
                return SimpleNamespace(content=content, raw=None)

        tool = FakeTool("retrieve_hessian_law_de")
        evidence = {"case_id": "dienstreiseantrag-01", "documents": {}}
        model = FakeModel()
        knowledge, aspects, iterations = identify_key_aspects(
            "dienstreiseantrag-01", evidence, [tool], model
        )
        self.assertEqual(2, iterations)
        self.assertEqual(2, model.calls)
        self.assertEqual(["x", "y"], [hit["doc_id"] for hit in knowledge])
        self.assertEqual("A1-Bescheinigung Ausland", tool.queries[1])
        self.assertEqual(1, len(aspects))

    def test_stops_after_max_iterations_even_if_still_insufficient(self):
        class FakeTool:
            def __init__(self, name):
                self.name = name
                self.calls = 0

            def __call__(self, query, max_results):
                self.calls += 1
                return json.dumps([{"corpus": "hessian-law-de", "doc_id": "x", "score": 1.0}])

        class FakeModel:
            def __init__(self):
                self.calls = 0

            def generate(self, messages, **_kwargs):
                self.calls += 1
                return SimpleNamespace(
                    content=json.dumps(
                        {"aspects": [], "sufficient": False, "follow_up_query": "noch unklar"}
                    ),
                    raw=None,
                )

        tool = FakeTool("retrieve_hessian_law_de")
        evidence = {"case_id": "dienstreiseantrag-01", "documents": {}}
        _knowledge, _aspects, iterations = identify_key_aspects(
            "dienstreiseantrag-01", evidence, [tool], FakeModel(), max_iterations=2
        )
        self.assertEqual(2, iterations)
        self.assertEqual(2, tool.calls)


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
        self.assertIsNone(entry["parent_event_id"])
        self.assertTrue(entry["event_id"])

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

    def test_chains_successive_events_in_the_same_case_via_parent_event_id(self):
        with self._capture_stdout() as output:
            with case_context("dienstreiseantrag-09"):
                first = log_event("tool_call", tool="a", input={}, output={})
                second = log_event("tool_call", tool="b", input={}, output={})

        entries = self._json_lines(output)
        self.assertIsNone(entries[0]["parent_event_id"])
        self.assertEqual(first, entries[0]["event_id"])
        self.assertEqual(first, entries[1]["parent_event_id"])
        self.assertEqual(second, entries[1]["event_id"])

    def test_resumes_the_chain_across_separate_case_context_entries(self):
        with self._capture_stdout() as output:
            with case_context("dienstreiseantrag-10"):
                first = log_event("tool_call", tool="a")
            with case_context("dienstreiseantrag-10"):
                second = log_event("model_call")

        entries = self._json_lines(output)
        self.assertEqual(first, entries[1]["parent_event_id"])
        self.assertEqual(second, entries[1]["event_id"])

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
            log_path = Path(tmp) / "run-trace.jsonl.log.gz"
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

    def _json_lines(self, output) -> list[dict]:
        return [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]

    def _single_json_line(self, output) -> dict:
        lines = self._json_lines(output)
        self.assertEqual(1, len(lines))
        return lines[0]


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
        # The chain must be unbroken: every event but the first has a parent
        # among the previously logged events.
        self.assertIsNone(entries[0]["parent_event_id"])
        logged_ids = {entry["event_id"] for entry in entries}
        for entry in entries[1:]:
            self.assertIn(entry["parent_event_id"], logged_ids)


if __name__ == "__main__":
    unittest.main()


