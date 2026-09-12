#!/usr/bin/env python
"""Fetch and cache official NTCIR proceedings and supplemental indexes."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ntcir_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ntcir"
LOGS_DIR = PROJECT_ROOT / "logs"

PUBLICATIONS_URL = "https://research.nii.ac.jp/ntcir/publication1-en.html"
DBLP_URL = "https://dblp.org/db/conf/ntcir/index.html"
TIRA_TASKS_URL = "https://www.tira.io/tasks"
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 0.5
USER_AGENT = "uniagent-corpus-builder/0.3"
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"fetch_ntcir_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Decode HTML using its declared charset rather than requests' Latin-1 default."""
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


def _link_score(href: str, text: str, edition: int) -> int:
    """Score likely NTCIR table-of-contents links on an edition index page."""
    lowered_href = href.casefold()
    lowered_text = text.casefold()
    if "evia" in lowered_href or "evia" in lowered_text:
        return -100
    score = 0
    if "toc" in lowered_href or "table of contents" in lowered_text:
        score += 10
    if "/ntcir/" in lowered_href or "ntcir/" in lowered_href:
        score += 5
    if "ntcir" in lowered_href or "ntcir" in lowered_text:
        score += 2
    if str(edition) in lowered_href or f"ntcir-{edition}" in lowered_text:
        score += 2
    if "abstract" in lowered_href or "author" in lowered_href or "organization" in lowered_href:
        score -= 4
    if "contact" in lowered_href or "contact" in lowered_text:
        score -= 8
    if href.casefold().endswith("index.html") and score < 5:
        score -= 1
    return score


def discover_toc_url(raw_html: str, proceedings_url: str, edition: int) -> str | None:
    """Find the official NTCIR table-of-contents page linked from an index."""
    soup = BeautifulSoup(raw_html, "lxml")
    proceedings_path = urlparse(proceedings_url).path.casefold()
    edition_scope = f"onlineproceedings{edition}"
    candidates: list[tuple[int, str]] = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        if urlparse(href).path.casefold().endswith((".pdf", ".ps", ".ps.gz", ".zip", ".bib")):
            continue
        absolute = urldefrag(urljoin(proceedings_url, href))[0]
        absolute_path = urlparse(absolute).path.casefold()
        if "onlineproceedings" in proceedings_path and edition_scope not in absolute_path:
            continue
        suffix = Path(absolute_path).suffix
        if suffix and suffix not in {".html", ".htm"}:
            continue
        if not suffix and not re.search(r"(?:toc|index|home|contents)(?:$|[/?#])", absolute_path):
            continue
        score = _link_score(href, link.get_text(" ", strip=True), edition)
        if score > 0:
            candidates.append((score, absolute))
    for frame in soup.find_all("frame", src=True):
        href = frame.get("src", "").strip()
        if not href:
            continue
        absolute = urldefrag(urljoin(proceedings_url, href))[0]
        absolute_path = urlparse(absolute).path.casefold()
        if "onlineproceedings" in proceedings_path and edition_scope not in absolute_path:
            continue
        suffix = Path(absolute_path).suffix
        if suffix and suffix not in {".html", ".htm"}:
            continue
        if not suffix and not re.search(r"(?:toc|index|home|contents)(?:$|[/?#])", absolute_path):
            continue
        score = _link_score(href, "", edition)
        if absolute.casefold().endswith(("/home.html", "/main.html")):
            score = max(score, 2)
        if score > 0:
            candidates.append((score, absolute))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[1]


def _has_pdf_link(raw_html: str) -> bool:
    soup = BeautifulSoup(raw_html, "lxml")
    return any(PDF_RE.search(link.get("href", "")) for link in soup.find_all("a", href=True))


def _edition_dir(edition: dict) -> Path:
    return RAW_DIR / "editions" / edition["collection_id"]


def fetch_edition(edition: dict, logger: logging.Logger, force: bool = False) -> None:
    """Fetch one official edition index, ToC, and resolved provenance metadata."""
    edition_dir = _edition_dir(edition)
    index_path = edition_dir / "index.html"
    metadata_path = edition_dir / "metadata.json"
    index_status = fetch_url(edition["proceedings_url"], index_path, logger, force=force)
    if index_status == "fetched":
        time.sleep(REQUEST_DELAY_SECONDS)
    if not index_path.exists():
        logger.warning("NTCIR-%s index unavailable; skipping ToC discovery", edition["edition"])
        return

    index_html = index_path.read_text(encoding="utf-8")
    toc_url = edition.get("toc_url") or discover_toc_url(
        index_html, edition["proceedings_url"], edition["edition"]
    )
    if toc_url is None and _has_pdf_link(index_html):
        toc_url = edition["proceedings_url"]
        logger.info("NTCIR-%s: using index page as ToC", edition["edition"])
    if toc_url is None:
        logger.warning("NTCIR-%s: no official ToC link found", edition["edition"])
    else:
        toc_path = edition_dir / "toc.html"
        previous_toc_url = None
        if metadata_path.exists():
            try:
                previous_toc_url = json.loads(metadata_path.read_text(encoding="utf-8")).get("toc_url")
            except (OSError, ValueError):
                previous_toc_url = None
        if toc_path.exists() and previous_toc_url and previous_toc_url != toc_url:
            logger.info("ToC URL changed for NTCIR-%s; refreshing %s", edition["edition"], toc_path)
            toc_path.unlink()
        for _ in range(2):
            toc_status = fetch_url(toc_url, toc_path, logger, force=force)
            if toc_status == "fetched":
                time.sleep(REQUEST_DELAY_SECONDS)
            if not toc_path.exists():
                break
            toc_html = toc_path.read_text(encoding="utf-8")
            if _has_pdf_link(toc_html):
                break
            nested_url = discover_toc_url(toc_html, toc_url, edition["edition"])
            if not nested_url or nested_url == toc_url:
                break
            # A frameset's home page is only an intermediate page. Replace the
            # cached content with the actual NTCIR ToC after following it.
            toc_url = nested_url
            if toc_path.exists():
                toc_path.unlink()

    metadata = {
        **edition,
        "toc_url": toc_url,
        "dblp_url": DBLP_URL,
        "tira_url": TIRA_TASKS_URL,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fetch_all(edition: int | None, logger: logging.Logger, force: bool = False) -> bool:
    """Fetch the official publication index, selected editions, DBLP, and TIRA."""
    editions = selected_editions(edition)
    if not editions:
        logger.error("no configured NTCIR edition %s", edition)
        return False
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetch_url(PUBLICATIONS_URL, RAW_DIR / "publication-index.html", logger, force=force)
    for item in editions:
        fetch_edition(item, logger, force=force)

    # These sources are supplemental evidence only. Their unavailability must
    # never prevent official NII pages from being collected.
    fetch_url(DBLP_URL, RAW_DIR / "dblp.html", logger, force=force)
    tira_status = fetch_url(TIRA_TASKS_URL, RAW_DIR / "tira-tasks.html", logger, force=force)
    if tira_status == "failed":
        logger.warning("TIRA task catalogue unavailable; TIRA cross-checks will be skipped")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache NTCIR proceedings and cross-check pages.")
    parser.add_argument("--edition", type=int, help="Fetch only one configured NTCIR edition number.")
    parser.add_argument("--refresh", action="store_true", help="Refetch cached HTML pages.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("fetch_ntcir")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if fetch_all(args.edition, logger, force=args.refresh) else 1)


if __name__ == "__main__":
    main()
