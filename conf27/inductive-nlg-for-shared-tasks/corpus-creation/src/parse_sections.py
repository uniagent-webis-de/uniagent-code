#!/usr/bin/env python
"""Stage 2 — parse cached CEUR-WS volume index pages into sections and papers,
cross-checked against cached DBLP working-notes records."""
import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CEUR_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ceur"
DBLP_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "dblp"
SECTIONS_DIR = PROJECT_ROOT / "data" / "intermediate" / "sections"
LOGS_DIR = PROJECT_ROOT / "logs"

CEUR_BASE_URL_TEMPLATE = "https://ceur-ws.org/Vol-{volume}/"

# Same volume map as src/fetch_volumes.py — kept in sync there; Stage 2 only needs
# volume -> (parent_venue, year) to name output files and locate the DBLP cache.
VOLUME_MAP = [
    {"parent_venue": "CLEF", "year": 2025, "volume": "4038"},
    {"parent_venue": "CLEF", "year": 2024, "volume": "3740"},
    {"parent_venue": "CLEF", "year": 2023, "volume": "3497"},
    {"parent_venue": "CLEF", "year": 2022, "volume": "3180"},
    {"parent_venue": "CLEF", "year": 2021, "volume": "2936"},
    {"parent_venue": "CLEF", "year": 2020, "volume": "2696"},
    {"parent_venue": "CLEF", "year": 2019, "volume": "2380"},
    {"parent_venue": "CLEF", "year": 2018, "volume": "2125"},
]


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"parse_sections_{timestamp}.log"

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


def normalize_title(title: str) -> str:
    """Lowercase and reduce to space-separated alphanumeric tokens — for matching across
    sources that format the same title slightly differently (line wraps, HTML entities,
    "CheckThat!-2023" vs "CheckThat! 2023", etc.). Punctuation is replaced with a space,
    not deleted, so hyphenated/adjacent words don't merge into one token."""
    lowered = title.lower()
    spaced = re.sub(r"[^a-z0-9]+", " ", lowered)
    return spaced.strip()


def parse_ceur_volume(raw_html: str, volume: str) -> list[dict]:
    """Parse a cached CEUR-WS index page into sections of papers, preserving
    published section boundaries and within-section order."""
    soup = BeautifulSoup(raw_html, "lxml")
    base_url = CEUR_BASE_URL_TEMPLATE.format(volume=volume)

    sections = []
    for session_span in soup.find_all("span", class_="CEURSESSION"):
        heading = session_span.find_parent(["h1", "h2", "h3", "h4"])
        if heading is None:
            continue
        lab_name = re.sub(r"\s+", " ", session_span.get_text(strip=True))

        paper_list = heading.find_next_sibling("ul")
        if paper_list is None:
            continue

        papers = []
        for position, item in enumerate(paper_list.find_all("li", recursive=False), start=1):
            title_span = item.find("span", class_="CEURTITLE")
            link = item.find("a", href=True)
            if title_span is None or link is None:
                continue

            title = re.sub(r"\s+", " ", title_span.get_text(strip=True))
            authors = [a.get_text(strip=True) for a in item.find_all("span", class_="CEURAUTHOR")]
            pdf_url = base_url + link["href"]

            papers.append({
                "title": title,
                "authors": authors,
                "pdf_url": pdf_url,
                "position_in_section": position,
            })

        sections.append({"lab_name": lab_name, "papers": papers})

    return sections


def parse_dblp_titles(raw_html: str) -> dict[str, list[str]]:
    """Parse a cached DBLP working-notes page into {normalized_title: [authors]},
    used only as a cross-check lookup in Stage 2 — not a source of new papers."""
    soup = BeautifulSoup(raw_html, "lxml")
    lookup: dict[str, list[str]] = {}

    for entry in soup.select("li.entry.inproceedings"):
        title_span = entry.find("span", class_="title")
        if title_span is None:
            continue
        title = title_span.get_text(strip=True).rstrip(".")
        authors = []
        for author_span in entry.find_all("span", itemprop="author"):
            name_span = author_span.find("span", itemprop="name")
            if name_span is not None:
                authors.append(name_span.get_text(strip=True))
        lookup[normalize_title(title)] = authors

    return lookup


def cross_check_dblp(sections: list[dict], dblp_lookup: dict[str, list[str]], logger: logging.Logger) -> None:
    """Annotate each paper in-place with dblp_match, preferring DBLP's author spelling
    when matched. CEUR's TOC remains authoritative for which papers exist."""
    unmatched = 0
    total = 0
    for section in sections:
        for paper in section["papers"]:
            total += 1
            key = normalize_title(paper["title"])
            match = dblp_lookup.get(key)
            paper["dblp_match"] = match is not None
            if match:
                paper["authors"] = match
            else:
                unmatched += 1

    if total:
        logger.info("DBLP cross-check: %d/%d papers matched", total - unmatched, total)
    if unmatched:
        logger.warning("DBLP cross-check: %d papers had no DBLP match (likely title-normalization miss)", unmatched)


def parse_and_write(entry: dict, logger: logging.Logger) -> None:
    volume = entry["volume"]
    ceur_path = CEUR_RAW_DIR / f"Vol-{volume}.html"
    dblp_path = DBLP_RAW_DIR / f"{entry['parent_venue']}{entry['year']}.html"

    if not ceur_path.exists():
        logger.error("missing cached CEUR page for volume %s (%s) — run fetch_volumes.py first", volume, ceur_path)
        return

    raw_html = ceur_path.read_text(encoding="utf-8")
    sections = parse_ceur_volume(raw_html, volume)
    logger.info("volume %s: parsed %d sections, %d papers", volume, len(sections), sum(len(s["papers"]) for s in sections))

    if dblp_path.exists():
        dblp_lookup = parse_dblp_titles(dblp_path.read_text(encoding="utf-8"))
        cross_check_dblp(sections, dblp_lookup, logger)
    else:
        logger.warning("no cached DBLP page for volume %s — skipping cross-check, dblp_match left unset", volume)
        for section in sections:
            for paper in section["papers"]:
                paper["dblp_match"] = None

    SECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SECTIONS_DIR / f"{volume}.json"
    out_path.write_text(
        json.dumps({
            "volume": volume,
            "parent_venue": entry["parent_venue"],
            "year": entry["year"],
            "sections": sections,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("wrote %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse cached CEUR-WS volume index pages into sections and papers.")
    parser.add_argument("--volume", type=str, default=None, help="Parse only this CEUR-WS volume number (e.g. 3497). Default: parse all volumes in the map.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("parse_sections")
    logger.info("logging to %s", log_path)

    volumes = VOLUME_MAP
    if args.volume is not None:
        volumes = [entry for entry in VOLUME_MAP if entry["volume"] == args.volume]
        if not volumes:
            logger.error("volume %s not found in VOLUME_MAP", args.volume)
            sys.exit(1)

    for entry in volumes:
        parse_and_write(entry, logger)


if __name__ == "__main__":
    main()
