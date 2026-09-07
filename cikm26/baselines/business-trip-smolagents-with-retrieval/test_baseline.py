import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from predict import (
    build_case_evidence,
    build_retrieval_query,
    decide_case,
    gather_case_knowledge,
    input_cases,
    parse_decision,
)
from retrieval_tools import (
    build_retrieval_tools,
    discover_corpora,
    document_text,
    infer_language,
    read_documents,
)


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
        model = FakeModel()
        decision = decide_case("dienstreiseantrag-01", evidence, knowledge, model)
        self.assertEqual("abgelehnt", decision["result"])
        self.assertIn("external_knowledge", model.messages[1]["content"])
        self.assertIn("bahn-rechnung-kassel-leipzig.pdf", model.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
