#!/usr/bin/env python
"""Fetch and cache official FIRE proceedings and supplemental indexes."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fire_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "fire"
LOGS_DIR = PROJECT_ROOT / "logs"

TIRA_TASKS_URL = "https://www.tira.io/tasks"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.35
USER_AGENT = "uniagent-corpus-builder/0.4"


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_fire_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def _response_text(response: requests.Response) -> str:
    """Decode HTML using its declared charset when one is present."""
    payload = getattr(response, "content", b"")
    if payload:
        detected = BeautifulSoup(payload, "lxml").original_encoding
        encoding = detected or getattr(response, "encoding", None) or "utf-8"
        try:
            return payload.decode(encoding, errors="replace")
        except (LookupError, UnicodeError):
            return payload.decode("utf-8", errors="replace")
    return response.text


def fetch_url(url: str, destination: Path, logger: logging.Logger, force: bool = False) -> str:
    """Fetch one page once and return ``cached``, ``fetched``, or ``failed``."""
    if destination.exists() and not force:
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
    destination.write_text(_response_text(response), encoding="utf-8")
    logger.info("fetched: %s status=%d -> %s", url, response.status_code, destination)
    return "fetched"


def fetch_edition(edition: dict, logger: logging.Logger, force: bool = False) -> None:
    """Fetch one FIRE edition's authoritative and supplemental pages."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    ceur_volume = edition.get("ceur_volume")
    if ceur_volume:
        fetch_url(
            edition["proceedings_url"],
            edition_dir / "proceedings.html",
            logger,
            force=force,
        )
        time.sleep(REQUEST_DELAY_SECONDS)
    else:
        # For older ACM/Springer editions, the official FIRE archive page is the
        # discovery source.  The proceedings landing page is retained as
        # provenance but is not assumed to expose downloadable papers.
        fetch_url(
            edition["proceedings_url"],
            edition_dir / "proceedings.html",
            logger,
            force=force,
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    fetch_url(edition["official_url"], edition_dir / "official.html", logger, force=force)
    time.sleep(REQUEST_DELAY_SECONDS)
    fetch_url(
        edition["dblp_url"],
        RAW_DIR / "dblp" / f"{edition['collection_id']}.html",
        logger,
        force=force,
    )
    time.sleep(REQUEST_DELAY_SECONDS)


def fetch_all(year: int | None, logger: logging.Logger, force: bool = False) -> bool:
    """Fetch all selected editions; unavailable older pages remain auditable."""
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured FIRE edition for year %s", year)
        return False
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for edition in editions:
        fetch_edition(edition, logger, force=force)

    # TIRA is supplemental evidence only. A service outage must not prevent the
    # authoritative FIRE collector from running.
    fetch_url(TIRA_TASKS_URL, RAW_DIR / "tira-tasks.html", logger, force=force)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache official FIRE proceedings and indexes.")
    parser.add_argument("--year", type=int, help="Fetch only one configured FIRE year.")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached source pages.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_fire")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if fetch_all(args.year, logger, force=args.refresh) else 1)


if __name__ == "__main__":
    main()
