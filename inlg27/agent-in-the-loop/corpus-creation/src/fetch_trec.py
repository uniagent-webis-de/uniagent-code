#!/usr/bin/env python
"""Fetch and cache official TREC proceedings and cross-check pages."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trec_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "trec"
DBLP_RAW_DIR = RAW_DIR / "dblp"
LOGS_DIR = PROJECT_ROOT / "logs"

MASTER_URL = "https://trec.nist.gov/proceedings/proceedings.html"
TIRA_TASKS_URL = "https://www.tira.io/tasks"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.5
USER_AGENT = "uniagent-corpus-builder/0.1"


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_trec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Fetch a URL once and return ``cached``, ``fetched``, or ``failed``."""
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
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return "failed"
    logger.info("fetched: %s status=%d -> %s", url, response.status_code, destination)
    if response.status_code != 200:
        logger.warning("non-200 status for %s: %d", url, response.status_code)
        return "failed"
    destination.write_text(response.text, encoding="utf-8")
    return "fetched"


def https_url(url: str) -> str:
    """Upgrade legacy HTTP links in NIST pages without changing their path."""
    parsed = urlparse(url)
    if parsed.scheme != "http":
        return url
    return urlunparse(("https", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def discover_track_url(raw_html: str, proceedings_url: str) -> str | None:
    """Find an official NIST index grouped by track from a proceedings page."""
    soup = BeautifulSoup(raw_html, "lxml")
    candidates: list[tuple[int, str]] = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).lower()
        href_lower = href.lower()
        if href.startswith("#"):
            continue
        score = 0
        if "xref" in href_lower:
            score += 4
        if "track" in href_lower:
            score += 3
        if "track" in text:
            score += 2
        if "index" in text or "indexed" in text:
            score += 1
        if score:
            candidates.append((score, https_url(urljoin(proceedings_url, href))))
    return max(candidates)[1] if candidates else None


def dblp_url(year: int) -> str:
    """Return the conventional DBLP TREC proceedings page URL."""
    return f"https://dblp.org/db/conf/trec/trec{year}.html"


def fetch_edition(edition: dict, logger: logging.Logger) -> None:
    collection_id = edition["collection_id"]
    year_dir = RAW_DIR / "years" / collection_id
    proceedings_path = year_dir / "proceedings.html"
    status = fetch_url(edition["proceedings_url"], proceedings_path, logger)
    if status == "fetched":
        time.sleep(REQUEST_DELAY_SECONDS)
    if status == "failed":
        logger.warning("skipping track-page discovery for TREC %s", edition["year"])
    elif proceedings_path.exists():
        track_url = discover_track_url(
            proceedings_path.read_text(encoding="utf-8"), edition["proceedings_url"]
        )
        if track_url:
            edition["track_url"] = track_url
            track_path = year_dir / "tracks.html"
            track_status = fetch_url(track_url, track_path, logger)
            if track_status == "fetched":
                time.sleep(REQUEST_DELAY_SECONDS)
        else:
            logger.warning("TREC %s: no official track index link found", edition["year"])

    DBLP_RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetch_url(dblp_url(edition["year"]), DBLP_RAW_DIR / f"{collection_id}.html", logger)


def fetch_all(year: int | None, logger: logging.Logger) -> bool:
    """Fetch the master index, selected proceedings, and optional cross-check pages."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetch_url(MASTER_URL, RAW_DIR / "proceedings-index.html", logger)
    for edition in selected_editions(year):
        fetch_edition(dict(edition), logger)

    # TIRA is supplemental evidence only. A service outage must not prevent the
    # authoritative NIST collector from running.
    tira_status = fetch_url(TIRA_TASKS_URL, RAW_DIR / "tira-tasks.html", logger)
    if tira_status == "failed":
        logger.warning("TIRA task catalogue unavailable; TIRA cross-checks will be skipped")
    return bool(selected_editions(year))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache TREC proceedings and cross-check pages.")
    parser.add_argument("--year", type=int, help="Fetch only one configured TREC year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_trec")
    logger.info("logging to %s", log_path)
    if not fetch_all(args.year, logger):
        logger.error("no configured TREC edition for year %s", args.year)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
