import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import Mock, patch

from tira.third_party_integrations import ir_datasets

import event_logging
from baseline import (
    create_index,
    detect_query_language,
    reorder_with_relevant_first,
    run_agentic_retrieval,
    search,
)
from retrieval_tools import (
    ComputeNdcgTool,
    JudgeRelevanceTool,
    QueryJudgmentStore,
    ReformulateQueryTool,
    ndcg_at_k,
)


@contextmanager
def persisted_dataset(queries: list[dict], documents: list[dict]) -> Iterator:
    with tempfile.TemporaryDirectory() as temporary_directory:
        dataset_directory = Path(temporary_directory)
        (dataset_directory / "queries.jsonl").write_text(
            "".join(json.dumps(query) + "\n" for query in queries), encoding="utf-8"
        )
        (dataset_directory / "documents.jsonl").write_text(
            "".join(json.dumps(document) + "\n" for document in documents), encoding="utf-8"
        )
        yield ir_datasets.load(str(dataset_directory))


def mock_model(*responses: str) -> Mock:
    model = Mock()
    model.generate.side_effect = [Mock(content=response) for response in responses]
    return model


class NdcgTest(unittest.TestCase):
    def test_perfect_ranking_scores_one(self) -> None:
        judgments = {"a": 3, "b": 2, "c": 0}
        self.assertAlmostEqual(ndcg_at_k(["a", "b", "c"], judgments), 1.0)

    def test_reversed_ranking_scores_below_one(self) -> None:
        judgments = {"a": 3, "b": 2, "c": 1}
        score_perfect = ndcg_at_k(["a", "b", "c"], judgments)
        score_reversed = ndcg_at_k(["c", "b", "a"], judgments)
        self.assertLess(score_reversed, score_perfect)

    def test_no_positive_judgments_scores_zero(self) -> None:
        self.assertEqual(ndcg_at_k(["a", "b"], {"a": 0, "b": 0}), 0.0)

    def test_unjudged_docnos_are_treated_as_not_relevant(self) -> None:
        judgments = {"a": 2}
        self.assertAlmostEqual(ndcg_at_k(["unjudged", "a"], judgments), ndcg_at_k(["x", "a"], judgments))

    def test_cutoff_ignores_documents_beyond_k(self) -> None:
        judgments = {str(i): 1 for i in range(15)}
        ranked = [str(i) for i in range(15)]
        self.assertAlmostEqual(ndcg_at_k(ranked, judgments, k=10), 1.0)


class JudgeRelevanceToolTest(unittest.TestCase):
    def test_stores_valid_judgments(self) -> None:
        model = mock_model(json.dumps({"judgments": [{"docno": "a", "relevance": 3}, {"docno": "b", "relevance": 0}]}))
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)

        result = json.loads(
            tool.forward("q1", "travel expenses", [{"docno": "a", "snippet": "..."}, {"docno": "b", "snippet": "..."}])
        )

        self.assertEqual(result["judgments"], {"a": 3, "b": 0})
        self.assertEqual(store.get_judgments("q1"), {"a": 3, "b": 0})

    def test_rejects_docno_not_among_candidates_when_no_other_judgment_is_valid(self) -> None:
        model = mock_model(json.dumps({"judgments": [{"docno": "unknown", "relevance": 1}]}))
        tool = JudgeRelevanceTool(model, QueryJudgmentStore())

        with self.assertRaisesRegex(ValueError, "did not return any usable judgments"):
            tool.forward("q1", "query", [{"docno": "a", "snippet": "..."}])

    def test_rejects_out_of_range_relevance_when_no_other_judgment_is_valid(self) -> None:
        model = mock_model(json.dumps({"judgments": [{"docno": "a", "relevance": 9}]}))
        tool = JudgeRelevanceTool(model, QueryJudgmentStore())

        with self.assertRaisesRegex(ValueError, "did not return any usable judgments"):
            tool.forward("q1", "query", [{"docno": "a", "snippet": "..."}])

    def test_caps_judgments_at_twenty_candidates(self) -> None:
        judgments = [{"docno": str(i), "relevance": 1} for i in range(25)]
        model = mock_model(json.dumps({"judgments": judgments}))
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)
        candidates = [{"docno": str(i), "snippet": "x"} for i in range(25)]

        tool.forward("q1", "query", candidates)

        self.assertEqual(len(store.get_judgments("q1")), 20)

    def test_rejects_empty_candidates(self) -> None:
        tool = JudgeRelevanceTool(Mock(), QueryJudgmentStore())
        with self.assertRaisesRegex(ValueError, "candidates must not be empty"):
            tool.forward("q1", "query", [])

    def test_parses_ndjson_style_response_with_one_object_per_candidate(self) -> None:
        """Regression test: models sometimes ignore the requested single
        {"judgments": [...]} object and instead answer with one bare JSON
        object per candidate (NDJSON-style), e.g.:
            {"docno": "a", "relevance": 3}
            {"docno": "b", "relevance": 0}
        A naive "find the first top-level JSON value" parser only captures
        the first object here (a bare judgment without a 'judgments' key),
        which used to raise "Model did not return a non-empty 'judgments'
        list: {'docno': 'a', 'relevance': 3}". All of them must be parsed."""
        model = mock_model(
            '{"docno": "a", "relevance": 3}\n{"docno": "b", "relevance": 0}\n{"docno": "c", "relevance": 1}'
        )
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)
        candidates = [{"docno": docno, "snippet": "..."} for docno in ("a", "b", "c")]

        tool.forward("q1", "query", candidates)

        self.assertEqual(store.get_judgments("q1"), {"a": 3, "b": 0, "c": 1})

    def test_parses_bare_json_array_response(self) -> None:
        model = mock_model(
            json.dumps([{"docno": "a", "relevance": 2}, {"docno": "b", "relevance": 1}])
        )
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)
        candidates = [{"docno": "a", "snippet": "..."}, {"docno": "b", "snippet": "..."}]

        tool.forward("q1", "query", candidates)

        self.assertEqual(store.get_judgments("q1"), {"a": 2, "b": 1})

    def test_parses_single_bare_judgment_object(self) -> None:
        model = mock_model(json.dumps({"docno": "a", "relevance": 3}))
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)

        tool.forward("q1", "query", [{"docno": "a", "snippet": "..."}])

        self.assertEqual(store.get_judgments("q1"), {"a": 3})

    def test_skips_hallucinated_docno_but_keeps_valid_judgments(self) -> None:
        """Regression test: a model that mostly follows instructions but
        also returns one extra judgment for a docno that was never among the
        candidates (e.g. a hallucinated/mistyped UUID, or an illustrative
        example JSON object caught by the lenient multi-object parser) must
        not abort the whole call - the unusable entry is skipped and the
        valid ones are still stored."""
        model = mock_model(
            json.dumps(
                {
                    "judgments": [
                        {"docno": "a", "relevance": 3},
                        {"docno": "74ae8556-feb0-4b80-a70e-9566acb8360b", "relevance": 2},
                        {"docno": "b", "relevance": 0},
                    ]
                }
            )
        )
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)
        candidates = [{"docno": "a", "snippet": "..."}, {"docno": "b", "snippet": "..."}]

        result = json.loads(tool.forward("q1", "query", candidates))

        self.assertEqual(result["judgments"], {"a": 3, "b": 0})
        self.assertEqual(store.get_judgments("q1"), {"a": 3, "b": 0})

    def test_skips_out_of_range_relevance_but_keeps_valid_judgments(self) -> None:
        model = mock_model(
            json.dumps(
                {
                    "judgments": [
                        {"docno": "a", "relevance": 3},
                        {"docno": "b", "relevance": 99},
                    ]
                }
            )
        )
        store = QueryJudgmentStore()
        tool = JudgeRelevanceTool(model, store)
        candidates = [{"docno": "a", "snippet": "..."}, {"docno": "b", "snippet": "..."}]

        tool.forward("q1", "query", candidates)

        self.assertEqual(store.get_judgments("q1"), {"a": 3})

    def test_raises_only_if_every_entry_is_unusable(self) -> None:
        model = mock_model(
            json.dumps({"judgments": [{"docno": "unknown-1", "relevance": 1}, {"docno": "unknown-2", "relevance": 2}]})
        )
        tool = JudgeRelevanceTool(model, QueryJudgmentStore())
        candidates = [{"docno": "a", "snippet": "..."}]

        with self.assertRaisesRegex(ValueError, "did not return any usable judgments"):
            tool.forward("q1", "query", candidates)


class ComputeNdcgToolTest(unittest.TestCase):
    def test_requires_prior_judgments(self) -> None:
        tool = ComputeNdcgTool(QueryJudgmentStore())
        with self.assertRaisesRegex(ValueError, "call judge_relevance first"):
            tool.forward("q1", ["a", "b"])

    def test_scores_against_stored_judgments(self) -> None:
        store = QueryJudgmentStore()
        store.set_judgments("q1", {"a": 3, "b": 0})
        tool = ComputeNdcgTool(store)

        result = json.loads(tool.forward("q1", ["a", "b"]))

        self.assertAlmostEqual(result["ndcg@10"], 1.0)

    def test_rejects_empty_ranking(self) -> None:
        store = QueryJudgmentStore()
        store.set_judgments("q1", {"a": 1})
        tool = ComputeNdcgTool(store)
        with self.assertRaisesRegex(ValueError, "ranked_docnos must not be empty"):
            tool.forward("q1", [])


class ReformulateQueryToolTest(unittest.TestCase):
    def test_returns_new_query_and_satisfaction_flag(self) -> None:
        model = mock_model(
            json.dumps({"query": "travel reimbursement deadline", "satisfied": False, "reasoning": "broader terms"})
        )
        tool = ReformulateQueryTool(model)

        result = json.loads(tool.forward("q1", "travel expenses", "travel expenses", 0.2))

        self.assertEqual(result["query"], "travel reimbursement deadline")
        self.assertFalse(result["satisfied"])

    def test_rejects_missing_query_in_response(self) -> None:
        model = mock_model(json.dumps({"satisfied": True}))
        tool = ReformulateQueryTool(model)
        with self.assertRaisesRegex(ValueError, "non-empty 'query'"):
            tool.forward("q1", "travel expenses", "travel expenses", 0.2)

    def test_tolerates_markdown_fenced_response(self) -> None:
        model = mock_model('```json\n{"query": "better query", "satisfied": true}\n```')
        tool = ReformulateQueryTool(model)

        result = json.loads(tool.forward("q1", "original", "original", 0.5))

        self.assertEqual(result["query"], "better query")
        self.assertTrue(result["satisfied"])


class ReorderWithRelevantFirstTest(unittest.TestCase):
    def test_moves_relevant_documents_to_top_preserving_order(self) -> None:
        import pandas as pd

        results = pd.DataFrame(
            {
                "qid": ["1", "1", "1", "1"],
                "docno": ["a", "b", "c", "d"],
                "rank": [0, 1, 2, 3],
                "score": [4.0, 3.0, 2.0, 1.0],
            }
        )
        judgments = {"c": 2, "a": 0, "d": 3}

        reordered = reorder_with_relevant_first(results, judgments)

        self.assertEqual(reordered["docno"].tolist(), ["c", "d", "a", "b"])
        self.assertEqual(reordered["rank"].tolist(), [0, 1, 2, 3])

    def test_returns_unchanged_ranking_without_relevant_documents(self) -> None:
        import pandas as pd

        results = pd.DataFrame({"qid": ["1", "1"], "docno": ["a", "b"], "rank": [0, 1], "score": [2.0, 1.0]})

        reordered = reorder_with_relevant_first(results, {})

        self.assertEqual(reordered["docno"].tolist(), ["a", "b"])

    def test_handles_empty_results(self) -> None:
        import pandas as pd

        results = pd.DataFrame(columns=["qid", "docno", "rank", "score"])
        self.assertTrue(reorder_with_relevant_first(results, {"a": 1}).empty)


class CreateIndexAndSearchTest(unittest.TestCase):
    def test_search_retrieves_documents_for_a_query(self) -> None:
        queries = [{"qid": "travel", "query": "Reisekosten", "original_query": {"language": "de"}}]
        documents = [
            {"doc_id": "travel-document", "text": "Die Erstattung der Reisekosten erfolgt monatlich."},
            {"doc_id": "unrelated-document", "text": "Allgemeine Universität."},
        ]

        with persisted_dataset(queries, documents) as dataset:
            index = create_index(dataset, "de")
            run = search(index, "de", "travel", "Reisekosten")

        self.assertEqual("travel-document", run.sort_values("rank").iloc[0]["docno"])

    def test_search_returns_empty_frame_for_stopword_only_query(self) -> None:
        queries = [{"qid": "stopwords", "query": "wie und wo", "original_query": {"language": "de"}}]
        documents = [{"doc_id": "document", "text": "Ein Dokument über Reisekosten."}]

        with persisted_dataset(queries, documents) as dataset:
            index = create_index(dataset, "de")
            run = search(index, "de", "stopwords", "wie und wo")

        self.assertTrue(run.empty)

    def test_rejects_unsupported_language(self) -> None:
        documents = [{"doc_id": "1", "text": "Du texte"}]
        with self.assertRaisesRegex(ValueError, "Unsupported language: fr"):
            create_index(_dataset_with_documents_only(documents), "fr")


def _dataset_with_documents_only(documents: list[dict]) -> Mock:
    docs = []
    for document in documents:
        doc = Mock()
        doc.doc_id = document["doc_id"]
        doc.default_text.return_value = document["text"]
        docs.append(doc)
    dataset = Mock()
    dataset.docs_iter.return_value = iter(docs)
    return dataset


class DetectQueryLanguageTest(unittest.TestCase):
    def test_detects_english_dataset(self) -> None:
        queries = [
            {"qid": "1", "query": "Travel reimbursement deadline", "original_query": {"language": "en"}},
        ]
        documents = [{"doc_id": "1", "text": "A document"}]

        with persisted_dataset(queries, documents) as dataset:
            self.assertEqual(detect_query_language(dataset), "en")

    def test_rejects_mixed_query_languages(self) -> None:
        queries = [
            {"qid": "1", "query": "a", "original_query": {"language": "de"}},
            {"qid": "2", "query": "b", "original_query": {"language": "en"}},
        ]
        documents = [{"doc_id": "1", "text": "A document"}]

        with persisted_dataset(queries, documents) as dataset:
            with self.assertRaisesRegex(ValueError, "found: de, en"):
                detect_query_language(dataset)


class RunAgenticRetrievalTest(unittest.TestCase):
    """End-to-end test with a real PyTerrier index but a scripted mock model,
    exercising judge -> compute_ndcg -> reformulate -> final reorder."""

    def setUp(self) -> None:
        event_logging.reset_state()

    def test_promotes_relevant_documents_after_reformulation(self) -> None:
        queries = [
            {
                "qid": "travel",
                "query": "travel reimbursement",
                "original_query": {"language": "en", "description": "travel expense reimbursement"},
            },
        ]
        documents = [
            {"doc_id": "reimbursement-document", "text": "Travel reimbursement is processed monthly."},
            {"doc_id": "unrelated-document", "text": "Laboratory safety instructions."},
            {"doc_id": "noise-document", "text": "Travel is sometimes just travel without any reimbursement."},
        ]

        # Round 1 (original query "reisen"): judge candidates, low nDCG.
        # Round 2 (reformulated query): judge is not re-called (judgments made
        # once), compute_ndcg scores the new ranking, model reports satisfied.
        model = mock_model(
            json.dumps(
                {
                    "judgments": [
                        {"docno": "reimbursement-document", "relevance": 3},
                        {"docno": "noise-document", "relevance": 0},
                    ]
                }
            ),
            json.dumps(
                {
                    "query": "travel expense reimbursement policy",
                    "satisfied": False,
                    "reasoning": "use domain-specific terms",
                }
            ),
            json.dumps({"satisfied": True}),
        )

        with persisted_dataset(queries, documents) as dataset:
            index = create_index(dataset, "en")
            with event_logging.log_to_file(Path(tempfile.mkstemp(suffix=".jsonl.log.gz")[1])):
                run = run_agentic_retrieval(dataset, index, "en", model, max_reformulations=1)

        self.assertGreaterEqual(len(run), 2)
        self.assertEqual(run.sort_values("rank").iloc[0]["docno"], "reimbursement-document")

    def test_falls_back_to_plain_bm25_ranking_when_judging_fails(self) -> None:
        """Regression test: if the model's judgments for a query are entirely
        unusable (e.g. every returned docno is hallucinated/mistyped and
        therefore not among that query's candidates), run_agentic_retrieval
        must not crash the whole run - it must log the failure and fall back
        to that query's plain BM25 ranking, and still process every query."""
        queries = [
            {"qid": "q1", "query": "travel reimbursement", "original_query": {"language": "en"}},
            {"qid": "q2", "query": "laboratory safety", "original_query": {"language": "en"}},
        ]
        documents = [
            {"doc_id": "reimbursement-document", "text": "Travel reimbursement is processed monthly."},
            {"doc_id": "safety-document", "text": "Laboratory safety instructions for staff."},
        ]

        # q1's judge_relevance response only contains a hallucinated docno
        # that is not among q1's candidates -> judge_relevance raises ->
        # run_agentic_retrieval must fall back instead of propagating.
        # q2 then succeeds normally (judge + satisfied reformulation).
        model = mock_model(
            json.dumps({"judgments": [{"docno": "74ae8556-feb0-4b80-a70e-9566acb8360b", "relevance": 2}]}),
            json.dumps({"judgments": [{"docno": "safety-document", "relevance": 3}]}),
            json.dumps({"satisfied": True}),
        )

        with persisted_dataset(queries, documents) as dataset:
            index = create_index(dataset, "en")
            with event_logging.log_to_file(Path(tempfile.mkstemp(suffix=".jsonl.log.gz")[1])):
                run = run_agentic_retrieval(dataset, index, "en", model, max_reformulations=1)

        # Both queries still contribute a ranking: q1 via the plain BM25
        # fallback, q2 via the normal judge/score/reorder path.
        self.assertEqual(set(run["qid"].astype(str)), {"q1", "q2"})
        q1_docnos = run[run["qid"].astype(str) == "q1"]["docno"].tolist()
        self.assertIn("reimbursement-document", q1_docnos)


if __name__ == "__main__":
    unittest.main()
