#!/usr/bin/env python
"""Fetch and cache official ACL Anthology SemEval proceedings pages."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.semeval_config import selected_volumes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "acl_anthology" / "semeval"
LOGS_DIR = PROJECT_ROOT / "logs"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = "uniagent-corpus-builder/0.2"


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_semeval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def fetch_url(url: str, destination: Path, logger: logging.Logger) -> str:
    """Fetch one official page unless it is already cached."""
    if destination.exists():
        logger.info("cache hit: %s -> %s", url, destination)
        return "cached"

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return "failed"

    if "semeval" not in response.text.lower():
        logger.error("fetched page does not look like SemEval proceedings: %s", url)
        return "failed"
    destination.write_text(response.text, encoding="utf-8")
    logger.info("fetched: %s status=%d -> %s", url, response.status_code, destination)
    return "fetched"


def fetch_all(year: int | None, logger: logging.Logger) -> bool:
    """Fetch configured proceedings and return whether every fetch succeeded."""
    volumes = selected_volumes(year)
    if not volumes:
        logger.error("no configured SemEval volume for year %s", year)
        return False

    successful = True
    for volume in volumes:
        destination = RAW_DIR / f"{volume['collection_id']}.html"
        status = fetch_url(volume["url"], destination, logger)
        if status == "failed":
            successful = False
        if status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)
    return successful


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache official SemEval proceedings pages.")
    parser.add_argument("--year", type=int, help="Fetch only one configured SemEval year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_semeval")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if fetch_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
