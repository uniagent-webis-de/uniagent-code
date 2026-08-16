import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from click.testing import CliRunner

from create_qrels import (
    build_topic_request,
    create_topic_judgments,
    create_umbrela_judge,
    get_openai_configuration,
    main,
    topic_path,
    write_qrels,
)


class Query:
    def __init__(self, query_id: str):
        self.query_id = query_id
        self.original_query = {
            "description": "A detailed question",
            "narrative": "Relevant documents answer the question.",
        }

    def default_text(self):
        return "query title"


class Document:
    def __init__(self, text: str):
        self.text = text

    def default_text(self):
        return self.text


class Documents:
    def __init__(self, documents: dict[str, Document]):
        self.documents = documents

    def get(self, document_id: str):
        return self.documents.get(document_id)


class Dataset:
    def __init__(self):
        self.query = Query("1")
        self.documents = Documents(
            {
                "a": Document("Document A"),
                "b": Document("Document B"),
            }
        )

    def queries_iter(self):
        return iter([self.query])

    def docs_store(self):
        return self.documents


class FakeJudge:
    def __init__(self):
        self.calls = []

    def judge(self, request):
        self.calls.append(request)
        return [
            {"judgment": index, "reasoning": f"Reason {index}"}
            for index, _ in enumerate(request["candidates"], start=1)
        ]


class ConfigurationTest(unittest.TestCase):
    def test_reads_openai_environment(self) -> None:
        environment = {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "OPENAI_MODEL": "model",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(environment, get_openai_configuration())

    def test_rejects_missing_openai_environment(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                get_openai_configuration()

    def test_creates_umbrela_judge_from_environment(self) -> None:
        judge = object()
        constructor = Mock(return_value=judge)
        module = ModuleType("umbrela.gpt_judge")
        module.GPTJudge = constructor
        environment = {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "OPENAI_MODEL": "model",
        }

        with patch.dict(os.environ, environment, clear=True), patch.dict(
            "sys.modules", {"umbrela.gpt_judge": module}
        ):
            self.assertIs(judge, create_umbrela_judge())

        constructor.assert_called_once_with(
            qrel="dl19-passage",
            model_name="model",
            prompt_type="bing",
            few_shot_count=0,
        )


class RequestTest(unittest.TestCase):
    def test_builds_topic_request_with_query_metadata_and_documents(self) -> None:
        dataset = Dataset()

        request = build_topic_request(
            dataset.query,
            ["a", "b"],
            dataset.documents,
        )

        self.assertEqual("1", request["query"]["qid"])
        self.assertIn("Description: A detailed question", request["query"]["text"])
        self.assertEqual(["a", "b"], [item["docid"] for item in request["candidates"]])
        self.assertEqual(
            "Document A",
            request["candidates"][0]["doc"]["segment"],
        )


class TopicJudgmentsTest(unittest.TestCase):
    def test_persists_requests_and_responses_and_skips_completed_topics(self) -> None:
        dataset = Dataset()
        pool = {"1": ["a", "b"]}
        judge = FakeJudge()

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            create_topic_judgments(dataset, pool, output, lambda: judge)
            create_topic_judgments(
                dataset,
                pool,
                output,
                lambda: self.fail("Judge must not be created for completed topics."),
            )

            request = json.loads(
                topic_path(output / "requests", "1").read_text(encoding="utf-8")
            )
            response = json.loads(
                topic_path(output / "responses", "1").read_text(encoding="utf-8")
            )

        self.assertEqual(1, len(judge.calls))
        self.assertEqual(["a", "b"], [item["docid"] for item in request["candidates"]])
        self.assertEqual([1, 2], [item["judgment"] for item in response["judgments"]])

    def test_rejects_stale_request(self) -> None:
        dataset = Dataset()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            request_path = topic_path(output / "requests", "1")
            request_path.parent.mkdir()
            request_path.write_text('{"stale": true}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "stale"):
                create_topic_judgments(
                    dataset,
                    {"1": ["a"]},
                    output,
                    FakeJudge,
                )

    def test_rejects_response_without_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            response_path = topic_path(output / "responses", "1")
            response_path.parent.mkdir()
            response_path.write_text('{"qid": "1"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "without request"):
                create_topic_judgments(
                    Dataset(),
                    {"1": ["a"]},
                    output,
                    FakeJudge,
                )


class QrelsTest(unittest.TestCase):
    def test_writes_deterministic_qrels_from_responses(self) -> None:
        pool = {"1": ["a", "b"]}
        response = {
            "qid": "1",
            "judgments": [
                {"docno": "a", "judgment": 3, "umbrela": {"judgment": 3}},
                {"docno": "b", "judgment": 0, "umbrela": {"judgment": 0}},
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            response_path = topic_path(output / "responses", "1")
            response_path.parent.mkdir()
            response_path.write_text(json.dumps(response), encoding="utf-8")

            qrels_path = write_qrels(pool, output)
            qrels = qrels_path.read_text(encoding="utf-8")

        self.assertEqual("1 0 a 3\n1 0 b 0\n", qrels)


class MainTest(unittest.TestCase):
    @patch("create_qrels.write_qrels")
    @patch("create_qrels.create_topic_judgments")
    @patch("create_qrels.get_pool")
    @patch("create_qrels.ir_datasets.load")
    def test_creates_pool_judgments_and_qrels(
        self,
        load,
        get_pool,
        create_topic_judgments,
        write_qrels,
    ) -> None:
        dataset = object()
        load.return_value = dataset
        get_pool.return_value = {"1": ["a"]}
        write_qrels.return_value = Path("output/qrels.txt")
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("runs").mkdir()
            result = runner.invoke(
                main,
                [
                    "--dataset",
                    "dataset",
                    "--runs",
                    "runs",
                    "--output",
                    "output",
                ],
            )

        self.assertEqual(0, result.exit_code, result.output)
        get_pool.assert_called_once_with(Path("runs"), 100, Path("output/pools"))
        create_topic_judgments.assert_called_once_with(
            dataset,
            {"1": ["a"]},
            Path("output"),
        )
        write_qrels.assert_called_once_with({"1": ["a"]}, Path("output"))


if __name__ == "__main__":
    unittest.main()
