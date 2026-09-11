#!/usr/bin/env python
"""Stage 4 — download accepted overview and notebook PDFs.

This stage owns PDF acquisition so downstream stages can treat the downloaded PDFs as
the canonical local inputs. It is deliberately resumable: successful files are kept and
failed files can be retried without downloading the rest again.
"""

import argparse
import json
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import document_pdf_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
LOGS_DIR = PROJECT_ROOT / "logs"
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "uniagent-corpus-builder/0.1"


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"download_papers_{timestamp}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    return log_path


def is_valid_pdf(path: Path) -> bool:
    """Return whether ``path`` looks like a non-empty PDF cache entry."""
    if not path.is_file() or path.stat().st_size < 5:
        return False
    try:
        with path.open("rb") as stream:
            return stream.read(5) == b"%PDF-"
    except OSError:
        return False


def download_pdf(url: str, destination: Path, logger: logging.Logger) -> bool:
    """Download one PDF atomically, preserving a valid existing cache entry."""
    if is_valid_pdf(destination):
        logger.info("cache hit: %s -> %s", url, destination)
        return True

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        logger.info("fetched: %s status=%d -> %s", url, response.status_code, destination)
        if response.status_code != 200:
            logger.error("download failed for %s: HTTP %d", url, response.status_code)
            return False
        if not response.content.startswith(b"%PDF-"):
            logger.error("download failed for %s: response is not a PDF", url)
            return False

        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(response.content)
        temporary_path.replace(destination)
        return True
    except requests.RequestException as exc:
        logger.error("download failed for %s: %s", url, exc)
        return False
    except OSError as exc:
        logger.error("could not save %s: %s", destination, exc)
        return False
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_tasks() -> list[dict]:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"missing {CANDIDATES_PATH} — run group_tasks.py first")
    return [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]


def process_document(task_id: str, role: str, pdf_url: str, logger: logging.Logger) -> bool:
    destination = document_pdf_path(task_id, role, pdf_url)
    return download_pdf(pdf_url, destination, logger)


def process_task(task: dict, logger: logging.Logger) -> list[str]:
    task_id = task["task_id"]
    failed = []
    if not process_document(task_id, "overview", task["overview"]["pdf_url"], logger):
        failed.append(task["overview"]["pdf_url"])
    for participant in task["participants"]:
        if not process_document(task_id, "participant", participant["pdf_url"], logger):
            failed.append(participant["pdf_url"])
    return failed


def document_jobs(tasks: list[dict]) -> list[tuple[str, str, str]]:
    """Return the overview and participant downloads as independent jobs."""
    jobs = []
    for task in tasks:
        jobs.append((task["task_id"], "overview", task["overview"]["pdf_url"]))
        jobs.extend(
            (task["task_id"], "participant", participant["pdf_url"])
            for participant in task["participants"]
        )
    return jobs


def process_documents(
    tasks: list[dict], logger: logging.Logger, workers: int
) -> list[str]:
    """Download documents concurrently while keeping each file atomic and resumable."""
    jobs = document_jobs(tasks)
    failed: list[str] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdf") as executor:
        futures = {
            executor.submit(
                process_document,
                task_id,
                role,
                pdf_url,
                logger,
            ): pdf_url
            for task_id, role, pdf_url in jobs
        }
        for future in as_completed(futures):
            pdf_url = futures[future]
            completed += 1
            try:
                if not future.result():
                    failed.append(pdf_url)
            except Exception:
                logger.exception("unexpected downloader error for %s", pdf_url)
                failed.append(pdf_url)
            logger.info(
                "download progress: %d/%d documents completed (%d failed)",
                completed,
                len(jobs),
                len(failed),
            )
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Download overview and notebook PDFs into the final task layout.")
    parser.add_argument("--confidence", choices=["high", "medium", "all"], default="high")
    parser.add_argument("--task-id", default=None, help="Process only one task id.")
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent PDF downloads (default: 8).",
    )
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers must be at least 1")

    setup_logging()
    logger = logging.getLogger("download_papers")
    try:
        tasks = load_tasks()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if args.task_id is not None:
        tasks = [task for task in tasks if task["task_id"] == args.task_id]
        if not tasks:
            logger.error("task_id %s not found", args.task_id)
            sys.exit(1)
    elif args.confidence != "all":
        tasks = [task for task in tasks if task["provenance"]["confidence"] == args.confidence]

    failed = process_documents(tasks, logger, args.workers)
    logger.info("processed %d tasks; %d PDFs failed", len(tasks), len(failed))
    if failed:
        for url in failed:
            logger.error("missing PDF after download attempt: %s", url)
        sys.exit(1)


if __name__ == "__main__":
    main()
