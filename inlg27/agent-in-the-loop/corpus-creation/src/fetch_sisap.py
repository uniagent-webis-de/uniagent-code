#!/usr/bin/env python
"""Fetch and cache official SISAP challenge, proceedings, and result sources."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sisap_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "sisap"
LOGS_DIR = PROJECT_ROOT / "logs"
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 0.25
USER_AGENT = "uniagent-corpus-builder/0.5"


def setup_logging() -> Path:
    """Create a readable write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_sisap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Decode a source response using the declared or detected encoding."""
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
    """Fetch one text source once and return ``cached``, ``fetched``, or ``failed``."""
    if destination.exists() and not force:
        logger.info("cache hit: %s -> %s", url, destination)
        return "cached"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,text/plain,*/*"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return "failed"
    destination.write_text(_response_text(response), encoding="utf-8")
    logger.info("fetched: %s status=%d -> %s", url, response.status_code, destination)
    return "fetched"


def _fetch_sources(
    edition: dict,
    logger: logging.Logger,
    force: bool,
) -> list[dict]:
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    sources: list[tuple[str, str]] = []
    field_filenames = {
        "official_url": "official.html",
        "tasks_url": "tasks.html",
        "methodology_url": "methodology.html",
        "evaluation_url": "evaluation.html",
        "proceedings_url": "proceedings.html",
        "conference_url": "conference.html",
        "overview_url": "overview_page.html",
        "leaderboard_url": "leaderboard.html",
        "accepted_url": "accepted.html",
    }
    seen_urls: set[str] = set()
    for field, filename in field_filenames.items():
        url = edition.get(field)
        if url and url not in seen_urls:
            sources.append((url, filename))
            seen_urls.add(url)
    for field, urls in edition.get("github_api_urls", {}).items():
        if urls not in seen_urls:
            sources.append((urls, f"github_api_{field}.json"))
            seen_urls.add(urls)
    for field, url in edition.get("github_files", {}).items():
        is_json = url.endswith(".json") or "/discussions/" in url or field.endswith("_discussion")
        suffix = ".json" if is_json else ".csv" if url.endswith(".csv") else ".md"
        if url not in seen_urls:
            sources.append((url, f"github_{field}{suffix}"))
            seen_urls.add(url)
    if edition.get("dblp_url") and edition["dblp_url"] not in seen_urls:
        sources.append((edition["dblp_url"], "dblp.html"))
        seen_urls.add(edition["dblp_url"])
    if edition.get("tira_url") and edition["tira_url"] not in seen_urls:
        sources.append((edition["tira_url"], "tira.html"))
        seen_urls.add(edition["tira_url"])

    statuses = []
    for url, filename in sources:
        destination = edition_dir / filename
        status = fetch_url(url, destination, logger, force=force)
        statuses.append({"url": url, "filename": filename, "status": status})
        if status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)
    return statuses


def fetch_edition(edition: dict, logger: logging.Logger, force: bool = False) -> None:
    """Fetch one complete SISAP edition into its resumable raw cache."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    statuses = _fetch_sources(edition, logger, force)
    metadata = {
        **edition,
        "sources": statuses,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    edition_dir.mkdir(parents=True, exist_ok=True)
    (edition_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failed = sum(1 for source in statuses if source["status"] == "failed")
    logger.info(
        "SISAP %s: cached %d sources (%d failed)", edition["year"], len(statuses), failed
    )


def fetch_all(year: int | None, logger: logging.Logger, force: bool = False) -> bool:
    """Fetch all configured editions; source outages remain auditable."""
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured SISAP edition for year %s", year)
        return False
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for edition in editions:
        fetch_edition(edition, logger, force=force)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache official SISAP challenge and proceedings sources."
    )
    parser.add_argument("--year", type=int, help="Fetch only one configured SISAP year.")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached source pages.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_sisap")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if fetch_all(args.year, logger, force=args.refresh) else 1)


if __name__ == "__main__":
    main()
