import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from create_pool import find_run_files, get_pool, main


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


class GetPoolTest(unittest.TestCase):
    def test_creates_and_persists_deduplicated_top_k_pool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runs = root / "runs"
            output = root / "output"
            write_run(
                runs / "first/run.txt",
                [("1", "a", 1, 3.0), ("1", "b", 2, 2.0), ("1", "c", 3, 1.0)],
            )
            write_run(
                runs / "second/run.txt.gz",
                [("1", "b", 1, 3.0), ("1", "c", 2, 2.0), ("1", "a", 3, 1.0)],
            )

            pool = get_pool(runs, k=2, output_directory=output)
            persisted_pool = json.loads(
                (output / "top-2-pool.json").read_text(encoding="utf-8")
            )

        expected = {"1": ["a", "b", "c"]}
        self.assertEqual(expected, pool)
        self.assertEqual(expected, persisted_pool)

    def test_loads_existing_pool_without_reading_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "output"
            output.mkdir()
            (output / "top-100-pool.json").write_text(
                '{"1": ["a", "b"]}\n',
                encoding="utf-8",
            )

            pool = get_pool(root / "missing-runs", 100, output)

        self.assertEqual({"1": ["a", "b"]}, pool)

    def test_rejects_invalid_k(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaisesRegex(ValueError, "k must be at least 1"):
                get_pool(root / "runs", 0, root / "output")


class MainTest(unittest.TestCase):
    def test_requires_dataset_runs_and_output(self) -> None:
        result = CliRunner().invoke(main, [])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Missing option '--dataset'", result.output)

    @patch("create_pool.get_pool")
    @patch("create_pool.ir_datasets.load")
    def test_loads_dataset_and_creates_pool(self, load, get_pool) -> None:
        get_pool.return_value = {"1": ["a", "b"]}
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
        load.assert_called_once_with("dataset")
        get_pool.assert_called_once_with(Path("runs"), 100, Path("output"))
        self.assertIn("2 query-document pairs", result.output)


if __name__ == "__main__":
    unittest.main()
