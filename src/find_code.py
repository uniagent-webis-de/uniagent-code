#!/usr/bin/env python
"""Stage 5 — resolve participant code links, scoped to the 44 high-confidence task
groups from Stage 3 (see PLAN.md section 3, Stage 5)."""
import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
PDF_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "pdf"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
LOGS_DIR = PROJECT_ROOT / "logs"

REQUEST_TIMEOUT_SECONDS = 30
HEAD_TIMEOUT_SECONDS = 10

CODE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.[a-z0-9.\-]+|zenodo\.org/record|huggingface\.co)/\S+",
    re.IGNORECASE,
)
TIRA_URL_RE = re.compile(r"https?://(?:www\.)?tira\.io/\S+", re.IGNORECASE)
TIRA_DOCKER_RE = re.compile(r"\bdocker\.io/[\w\-./:]+", re.IGNORECASE)

# Trailing punctuation that's part of the surrounding sentence, not the URL itself
# (e.g. "see https://github.com/x/y." at the end of a sentence).
TRAILING_PUNCTUATION_RE = re.compile(r"[.,;:)\]]+$")


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"find_code_{timestamp}.log"

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


def clean_url(url: str) -> str:
    return TRAILING_PUNCTUATION_RE.sub("", url)


def extract_links(text: str) -> tuple[list[str], list[str]]:
    code_urls = sorted({clean_url(u) for u in CODE_URL_RE.findall(text)})
    tira_refs = sorted({clean_url(u) for u in TIRA_URL_RE.findall(text)} | {clean_url(u) for u in TIRA_DOCKER_RE.findall(text)})
    return code_urls, tira_refs


def validate_url(url: str, logger: logging.Logger) -> str:
    """HEAD-check a code URL. Returns a status label; a dead link is kept (not dropped)
    since per PLAN.md it's still evidence the team had a repo."""
    try:
        response = requests.head(url, timeout=HEAD_TIMEOUT_SECONDS, allow_redirects=True, headers={"User-Agent": "uniagent-corpus-builder/0.1"})
        status = str(response.status_code)
    except requests.RequestException as exc:
        status = "unreachable"
        logger.warning("HEAD check failed for %s: %s", url, exc)
    logger.info("code URL check: %s -> %s", url, status)
    return status


def fetch_pdf(url: str, dest_path: Path, logger: logging.Logger) -> bool:
    if dest_path.exists():
        logger.info("cache hit: %s -> %s", url, dest_path)
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "uniagent-corpus-builder/0.1"})
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return False

    logger.info("fetched: %s status=%d -> %s", url, response.status_code, dest_path)
    if response.status_code != 200:
        logger.warning("non-200 status for %s: %d", url, response.status_code)
        return False

    dest_path.write_bytes(response.content)
    return True


def parse_pdf_text(pdf_path: Path, txt_path: Path, logger: logging.Logger) -> str | None:
    if txt_path.exists():
        logger.info("parse cache hit: %s", txt_path)
        return txt_path.read_text(encoding="utf-8")

    result = subprocess.run(
        ["lit", "parse", str(pdf_path), "--format", "text", "--no-ocr", "-o", str(txt_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("lit parse failed for %s: %s", pdf_path, result.stderr.strip())
        return None
    logger.info("parsed: %s -> %s", pdf_path, txt_path)
    return txt_path.read_text(encoding="utf-8")


def pdf_filename_for(pdf_url: str) -> str:
    stem = Path(urlparse(pdf_url).path).stem
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)


def process_participant(task_id: str, participant: dict, logger: logging.Logger) -> dict:
    pdf_url = participant["pdf_url"]
    stem = pdf_filename_for(pdf_url)
    pdf_dir = PDF_RAW_DIR / task_id
    pdf_path = pdf_dir / f"{stem}.pdf"
    txt_path = pdf_dir / f"{stem}.txt"

    if not fetch_pdf(pdf_url, pdf_path, logger):
        return {"pdf_url": pdf_url, "code_urls": [], "tira_refs": []}

    text = parse_pdf_text(pdf_path, txt_path, logger)
    if text is None:
        return {"pdf_url": pdf_url, "code_urls": [], "tira_refs": []}

    code_urls, tira_refs = extract_links(text)
    if not code_urls and not tira_refs:
        logger.info("%s: no code links found", pdf_url)
        return {"pdf_url": pdf_url, "code_urls": [], "tira_refs": tira_refs}

    validated = [{"url": url, "status": validate_url(url, logger)} for url in code_urls]
    return {"pdf_url": pdf_url, "code_urls": validated, "tira_refs": tira_refs}


def process_task(task: dict, logger: logging.Logger) -> list[dict]:
    task_id = task["task_id"]
    out_path = CODE_DIR / f"{task_id}.json"
    if out_path.exists():
        logger.info("code cache hit: %s", out_path)
        return json.loads(out_path.read_text(encoding="utf-8"))

    results = [process_participant(task_id, p, logger) for p in task["participants"]]

    CODE_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve participant code links for candidate tasks.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to process (default: high only).")
    parser.add_argument("--task-id", type=str, default=None, help="Process only this single task_id (for testing).")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("find_code")
    logger.info("logging to %s", log_path)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.task_id is not None:
        tasks = [t for t in tasks if t["task_id"] == args.task_id]
    elif args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]

    total_participants = 0
    with_code = 0
    for task in tasks:
        results = process_task(task, logger)
        total_participants += len(results)
        with_code += sum(1 for r in results if r["code_urls"] or r["tira_refs"])
        logger.info("%s: %d/%d participants have a resolved link", task["task_id"], sum(1 for r in results if r["code_urls"] or r["tira_refs"]), len(results))

    logger.info("processed %d tasks, %d participant papers: %d have at least one resolved code/TIRA link", len(tasks), total_participants, with_code)


if __name__ == "__main__":
    main()
