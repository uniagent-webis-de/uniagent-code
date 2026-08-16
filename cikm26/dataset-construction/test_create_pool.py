import gzip
import json
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from create_pool import create_pool, find_run_files, main, write_pool


class Query:
    def __init__(self, query_id: str):
        self.query_id = query_id


class Documents:
    def __init__(self, document_ids: set[str]):
        self.document_ids = document_ids

    def get(self, document_id: str):
        return document_id if document_id in self.document_ids else None


class Dataset:
    def __init__(self, query_ids: set[str], document_ids: set[str]):
        self.query_ids = query_ids
        self.document_ids = document_ids

    def queries_iter(self):
        return iter(Query(query_id) for query_id in self.query_ids)

    def docs_store(self):
        return Documents(self.document_ids)


def write_run(path: Path, rows: list[tuple[str, str, int, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        f"{qid} Q0 {docno} {rank} {score} test\n" for qid, docno, rank, score in rows
    )
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as output:
            output.write(content)
    else:
        path.write_text(content, encoding="utf-8")


class FindRunFilesTest(unittest.TestCase):
    def test_finds_plain_and_compressed_runs_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runs = Path(temporary_directory)
            write_run(runs / "a/run.txt", [("1", "a", 1, 1.0)])
            write_run(runs / "b/run.txt.gz", [("1", "b", 1, 1.0)])
            (runs / "ignored.txt").write_text("ignored", encoding="utf-8")

            self.assertEqual(
                [runs / "a/run.txt", runs / "b/run.txt.gz"],
                find_run_files(runs),
            )

    def test_rejects_directory_without_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "No run.txt"):
                find_run_files(Path(temporary_directory))


class CreatePoolTest(unittest.TestCase):
    def test_creates_deduplicated_top_k_pool(self) -> None:
        dataset = Dataset({"1"}, {"a", "b", "c"})
        with tempfile.TemporaryDirectory() as temporary_directory:
            runs = Path(temporary_directory)
            first = runs / "first.txt"
            second = runs / "second.txt"
            write_run(
                first,
                [("1", "a", 1, 3.0), ("1", "b", 2, 2.0), ("1", "c", 3, 1.0)],
            )
            write_run(
                second,
                [("1", "b", 1, 3.0), ("1", "c", 2, 2.0), ("1", "a", 3, 1.0)],
            )

            records = create_pool(dataset, [first, second], k=2)

        self.assertEqual(
            [
                {"qid": "1", "docno": "a"},
                {"qid": "1", "docno": "b"},
                {"qid": "1", "docno": "c"},
            ],
            records,
        )

    def test_rejects_unknown_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = Path(temporary_directory) / "run.txt"
            write_run(run, [("unknown", "a", 1, 1.0)])

            with self.assertRaisesRegex(ValueError, "unknown query ID"):
                create_pool(Dataset({"1"}, {"a"}), [run], k=100)

    def test_rejects_unknown_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = Path(temporary_directory) / "run.txt"
            write_run(run, [("1", "unknown", 1, 1.0)])

            with self.assertRaisesRegex(ValueError, "unknown document ID"):
                create_pool(Dataset({"1"}, {"a"}), [run], k=100)


class WritePoolTest(unittest.TestCase):
    def test_writes_jsonl_pool(self) -> None:
        records = [{"qid": "1", "docno": "a"}, {"qid": "1", "docno": "b"}]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_file = write_pool(records, Path(temporary_directory) / "output")
            actual = [
                json.loads(line)
                for line in output_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(records, actual)


class MainTest(unittest.TestCase):
    def test_requires_dataset_runs_and_output(self) -> None:
        result = CliRunner().invoke(main, [])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Missing option '--dataset'", result.output)


if __name__ == "__main__":
    unittest.main()
