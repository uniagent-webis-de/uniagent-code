#!/usr/bin/env python
"""Stage 4 — download accepted overview and notebook PDFs.

This stage owns PDF acquisition so downstream stages can treat the downloaded PDFs as
the canonical local inputs. It is deliberately resumable: successful files are kept and
failed files can be retried without downloading the rest again.
"""

import argparse
import json
import logging
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import demote, read_jsonl, write_jsonl
from src.corpus_paths import INTERMEDIATE_DIR, document_pdf_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
DOWNLOAD_FAILURES_PATH = INTERMEDIATE_DIR / "download_failures.jsonl"
LOGS_DIR = PROJECT_ROOT / "logs"
REQUEST_TIMEOUT_SECONDS = (10, 20)
MAX_DOWNLOAD_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1
NII_HOST = "research.nii.ac.jp"
NII_CURL_MAX_TIME_SECONDS = 60
NII_CURL_SPEED_LIMIT_BYTES = 1024
NII_CURL_SPEED_TIME_SECONDS = 10
NII_WGET_TIMEOUT_SECONDS = 20
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
    if urlparse(url).hostname == NII_HOST:
        return download_nii_pdf(url, destination, logger)

    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        temporary_path: Path | None = None
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
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
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                logger.error("download failed for %s: %s", url, exc)
                return False
            logger.warning(
                "download attempt %d/%d failed for %s; retrying: %s",
                attempt,
                MAX_DOWNLOAD_ATTEMPTS,
                url,
                exc,
            )
            time.sleep(RETRY_DELAY_SECONDS)
        except OSError as exc:
            logger.error("could not save %s: %s", destination, exc)
            return False
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def download_nii_pdf(url: str, destination: Path, logger: logging.Logger) -> bool:
    """Fetch NII's legacy PDFs with wget, falling back to bounded curl."""
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
            ) as stream:
                temporary_path = Path(stream.name)
            if shutil.which("wget"):
                command = [
                    "wget",
                    "--quiet",
                    "--timeout",
                    str(NII_WGET_TIMEOUT_SECONDS),
                    "--tries",
                    "1",
                    "--user-agent",
                    USER_AGENT,
                    "--output-document",
                    str(temporary_path),
                    url,
                ]
            else:
                command = [
                    "curl",
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--connect-timeout",
                    "8",
                    "--max-time",
                    str(NII_CURL_MAX_TIME_SECONDS),
                    "--speed-limit",
                    str(NII_CURL_SPEED_LIMIT_BYTES),
                    "--speed-time",
                    str(NII_CURL_SPEED_TIME_SECONDS),
                    "-A",
                    USER_AGENT,
                    "-o",
                    str(temporary_path),
                    url,
                ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            command_timeout = NII_WGET_TIMEOUT_SECONDS if command[0] == "wget" else NII_CURL_MAX_TIME_SECONDS
            try:
                stderr = process.communicate(timeout=command_timeout * 2 + 5)[1]
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stderr = process.communicate()[1]
                raise subprocess.TimeoutExpired(process.args, command_timeout * 2 + 5) from None
            if process.returncode == 0 and is_valid_pdf(temporary_path):
                temporary_path.replace(destination)
                logger.info("fetched with %s: %s -> %s", command[0], url, destination)
                return True
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            tool = command[0]
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                logger.error("download failed for %s with %s: %s", url, tool, detail or "unknown error")
                return False
            logger.warning("%s attempt %d/%d failed for %s; retrying: %s", tool, attempt, MAX_DOWNLOAD_ATTEMPTS, url, detail)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                logger.error("download failed for %s with %s: %s", url, command[0], exc)
                return False
            logger.warning("%s attempt %d/%d failed for %s; retrying: %s", command[0], attempt, MAX_DOWNLOAD_ATTEMPTS, url, exc)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        time.sleep(RETRY_DELAY_SECONDS)
    return False


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


def demote_failed_tasks(tasks: list[dict], failed_urls: list[str], logger: logging.Logger) -> set[str]:
    """Demote tasks whose required PDFs remain unavailable after the download attempt."""
    failed_set = set(failed_urls)
    failed_task_ids = {
        task["task_id"]
        for task in tasks
        if task["overview"]["pdf_url"] in failed_set
        or any(participant["pdf_url"] in failed_set for participant in task["participants"])
    }
    if not failed_task_ids or not CANDIDATES_PATH.exists():
        return failed_task_ids

    all_candidates = read_jsonl(CANDIDATES_PATH)
    failure_records = read_jsonl(DOWNLOAD_FAILURES_PATH)
    known_failures = {
        (record.get("task_id"), record.get("pdf_url"))
        for record in failure_records
    }
    for candidate in all_candidates:
        if candidate.get("task_id") not in failed_task_ids:
            continue
        failed_for_task = [
            url
            for url in failed_set
            if url == (candidate.get("overview") or {}).get("pdf_url")
            or any(url == participant.get("pdf_url") for participant in candidate.get("participants", []))
        ]
        demote(candidate, [f"required PDF download failed: {url}" for url in sorted(failed_for_task)])
        for url in sorted(failed_for_task):
            key = (candidate["task_id"], url)
            if key not in known_failures:
                failure_records.append(
                    {"task_id": candidate["task_id"], "pdf_url": url, "reason": "download_failed"}
                )
                known_failures.add(key)
        logger.warning(
            "%s demoted to review because %d required PDF(s) failed to download",
            candidate["task_id"], len(failed_for_task),
        )
    write_jsonl(all_candidates, CANDIDATES_PATH)
    write_jsonl(failure_records, DOWNLOAD_FAILURES_PATH)
    return failed_task_ids


def clear_recovered_failures(tasks: list[dict], logger: logging.Logger) -> None:
    """Remove failure records whose PDFs are now valid after a later retry."""
    if not DOWNLOAD_FAILURES_PATH.exists():
        return
    records = read_jsonl(DOWNLOAD_FAILURES_PATH)
    tasks_by_id = {task.get("task_id"): task for task in tasks}
    recovered: set[tuple[str, str]] = set()
    for record in records:
        task = tasks_by_id.get(record.get("task_id"))
        if task is None:
            continue
        url = record.get("pdf_url")
        required = [("overview", task.get("overview", {}).get("pdf_url"))]
        required.extend(("participant", paper.get("pdf_url")) for paper in task.get("participants", []))
        paths = [
            document_pdf_path(task["task_id"], role, required_url)
            for role, required_url in required
            if required_url
        ]
        current_url = any(url == required_url for _, required_url in required)
        task_complete = bool(paths) and all(is_valid_pdf(path) for path in paths)
        current_path_valid = False
        if current_url:
            role = "overview" if url == task.get("overview", {}).get("pdf_url") else "participant"
            current_path_valid = is_valid_pdf(document_pdf_path(task["task_id"], role, url))
        if task_complete or current_path_valid:
            recovered.add((record.get("task_id"), url))
            logger.info("clearing recovered download failure for %s: %s", record.get("task_id"), url)
    if recovered:
        write_jsonl(
            [
                record for record in records
                if (record.get("task_id"), record.get("pdf_url")) not in recovered
            ],
            DOWNLOAD_FAILURES_PATH,
        )


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
    clear_recovered_failures(tasks, logger)
    if failed:
        failed_task_ids = demote_failed_tasks(tasks, failed, logger)
        logger.info("automatically moved %d incomplete task(s) to review", len(failed_task_ids))
        for url in failed:
            logger.error("missing PDF after download attempt: %s", url)
        # A failed required document is a review decision, not a pipeline crash. The
        # affected task records are demoted before the next stage, so only complete
        # high-confidence tasks continue to parsing and final assembly.


if __name__ == "__main__":
    main()
