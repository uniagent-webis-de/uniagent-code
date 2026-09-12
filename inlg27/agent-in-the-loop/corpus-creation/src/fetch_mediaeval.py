#!/usr/bin/env python
"""Fetch and cache official MediaEval proceedings and supplemental indexes."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mediaeval_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "mediaeval"
LOGS_DIR = PROJECT_ROOT / "logs"

DBLP_URL_TEMPLATE = "https://dblp.org/db/conf/mediaeval/mediaeval{year}.html"
TIRA_TASKS_URL = "https://www.tira.io/tasks"
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 0.35
USER_AGENT = "uniagent-corpus-builder/0.5"
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
NON_HTML_SUFFIXES = {
    ".css", ".csv", ".doc", ".docx", ".gif", ".ico", ".jpeg", ".jpg",
    ".js", ".json", ".png", ".ppt", ".pptx", ".svg", ".tar", ".txt",
    ".xls", ".xlsx", ".xml", ".zip",
}
IGNORED_PATH_WORDS = {
    "about", "archive", "contact", "copyright", "history", "index",
    "news", "people", "privacy", "resources", "team", "workshop",
}


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_mediaeval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Decode HTML using the declared or detected encoding."""
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


def discover_task_urls(raw_html: str, base_url: str, year: int) -> list[str]:
    """Find likely official task pages without crawling unrelated navigation.

    Historical MediaEval sites use several incompatible layouts.  The fetcher
    therefore records same-site HTML links that have task-like URL or anchor
    evidence, while leaving the collector to apply the stricter paper checks.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    base_host = urlparse(base_url).netloc.casefold()
    scored: dict[str, int] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urldefrag(urljoin(base_url, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != base_host:
            continue
        suffix = Path(parsed.path.casefold()).suffix
        if suffix in NON_HTML_SUFFIXES or PDF_RE.search(parsed.path):
            continue
        path_text = parsed.path.casefold()
        anchor_text = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True).casefold())
        path_parts = {part for part in path_text.split("/") if part}
        if path_parts.intersection(IGNORED_PATH_WORDS) and not path_parts.intersection(
            {"task", "tasks", "track", "tracks", "challenge", "challenges"}
        ):
            continue
        score = 1
        if any(word in path_text for word in ("task", "track", "challenge", "session")):
            score += 3
        if any(word in anchor_text for word in ("task", "track", "challenge", "working note", "overview")):
            score += 3
        if "read more" in anchor_text:
            score += 2
        if str(year) in path_text or str(year) in anchor_text:
            score += 1
        if score >= 4:
            scored[absolute] = max(score, scored.get(absolute, 0))
    return [url for url, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))]


def fetch_task_pages(
    edition: dict, official_html: str, logger: logging.Logger, force: bool = False
) -> None:
    """Cache official task pages discovered from an edition landing page."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    task_urls = discover_task_urls(official_html, edition["official_url"], edition["year"])
    records = []
    for index, url in enumerate(task_urls, start=1):
        destination = edition_dir / f"task_{index:03d}.html"
        status = fetch_url(url, destination, logger, force=force)
        records.append({"url": url, "filename": destination.name, "status": status})
        if status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)
    (edition_dir / "task_pages.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("discovered %d official MediaEval task pages for %s", len(records), edition["year"])


def fetch_edition(edition: dict, logger: logging.Logger, force: bool = False) -> None:
    """Fetch one edition's proceedings, official page, and DBLP record."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    proceedings_path = edition_dir / "proceedings.html"
    official_path = edition_dir / "official.html"

    proceedings_status = fetch_url(
        edition["proceedings_url"], proceedings_path, logger, force=force
    )
    if proceedings_status == "fetched":
        time.sleep(REQUEST_DELAY_SECONDS)

    if edition["official_url"] == edition["proceedings_url"]:
        if proceedings_path.exists() and (force or not official_path.exists()):
            shutil.copyfile(proceedings_path, official_path)
            logger.info("reused proceedings cache as official cache: %s", official_path)
    else:
        official_status = fetch_url(edition["official_url"], official_path, logger, force=force)
        if official_status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)

    if official_path.exists():
        fetch_task_pages(
            edition,
            official_path.read_text(encoding="utf-8"),
            logger,
            force=force,
        )

    dblp_url = DBLP_URL_TEMPLATE.format(year=edition["year"])
    fetch_url(
        dblp_url,
        RAW_DIR / "dblp" / f"{edition['collection_id']}.html",
        logger,
        force=force,
    )
    metadata = {
        **edition,
        "dblp_url": dblp_url,
        "tira_url": TIRA_TASKS_URL,
    }
    metadata_path = edition_dir / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fetch_all(year: int | None, logger: logging.Logger, force: bool = False) -> bool:
    """Fetch all selected editions; source outages do not stop the scan."""
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured MediaEval edition for year %s", year)
        return False
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for edition in editions:
        fetch_edition(edition, logger, force=force)
    fetch_url(TIRA_TASKS_URL, RAW_DIR / "tira-tasks.html", logger, force=force)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache official MediaEval proceedings and indexes."
    )
    parser.add_argument("--year", type=int, help="Fetch only one configured MediaEval year.")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached source pages.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_mediaeval")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if fetch_all(args.year, logger, force=args.refresh) else 1)


if __name__ == "__main__":
    main()
