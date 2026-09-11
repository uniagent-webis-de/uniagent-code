#!/usr/bin/env python
"""Collect automatic TREC task candidates from official NIST proceedings.

NIST publishes several HTML layouts over the TREC history. Modern proceedings
use ``xref.html`` sections with a coordinator entry followed by participant
papers; older proceedings use an ``index.track.html`` page with named track
anchors and ``li``/``dt`` paper entries. The NIST grouping is authoritative.
DBLP and TIRA are supplemental cross-checks and never create papers.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import slugify, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, SCREENING_DIR
from src.fetch_trec import dblp_url, discover_track_url
from src.trec_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "trec"
LOGS_DIR = PROJECT_ROOT / "logs"

SUPPORTED_FORMATS = {
    ".pdf": "pdf",
    ".ps": "postscript",
    ".gz": "compressed",
    ".txt": "text",
}
OVERVIEW_RE = re.compile(
    r"\boverview\b|\bcoordinator\b|\btrack\s+(?:final\s+)?report\b|\btrack\s+report\b",
    re.IGNORECASE,
)
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
PAPER_RE = re.compile(r"\.(?:pdf|ps|ps\.gz|pdf\.gz|txt)(?:$|[?#])", re.IGNORECASE)
PAGE_RE = re.compile(r"\s*,?\s*page\s+\d+\s*$", re.IGNORECASE)
TEAM_RE = re.compile(r"^\s*\[([^\]]+)\]\s*", re.IGNORECASE)
SOURCE_ANCHOR_RE = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*([\"'])(?P<href>[^\"']+)\1[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_trec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def clean_text(value: str) -> str:
    """Collapse layout whitespace while preserving punctuation in paper titles."""
    return re.sub(r"\s+", " ", value).strip()


def paper_links(node, base_url: str) -> list[tuple[str, str]]:
    """Return supported source-file links as ``(format, absolute_url)`` pairs."""
    links: list[tuple[str, str]] = []
    for anchor in node.find_all("a", href=True):
        href = anchor["href"]
        path = urlparse(href).path.lower()
        file_format = None
        for suffix, candidate_format in SUPPORTED_FORMATS.items():
            if path.endswith(suffix) or path.endswith(suffix + ".gz"):
                file_format = candidate_format
                break
        if file_format is not None:
            links.append((file_format, urljoin(base_url, href)))
    return links


def choose_source_link(node, base_url: str) -> tuple[str | None, str | None]:
    """Prefer an official PDF, retaining the best legacy format when no PDF exists."""
    links = paper_links(node, base_url)
    for preferred in ("pdf", "postscript", "compressed", "text"):
        for file_format, url in links:
            if file_format == preferred:
                return file_format, url
    return None, None


def split_lines(node) -> list[str]:
    """Extract human-readable lines from a legacy HTML entry."""
    return [clean_text(line) for line in node.get_text("\n", strip=True).splitlines() if clean_text(line)]


def entry_title(node) -> str:
    """Extract a paper title from modern and legacy NIST entry markup."""
    bold = node.find("b")
    if bold is not None:
        title = clean_text(bold.get_text(" ", strip=True))
    else:
        lines = split_lines(node)
        title = lines[0] if lines else ""
        for line in lines:
            if not line.lower().startswith(("pdf file", "postscript file", "adobe portable")):
                title = line
                break
    title = PAGE_RE.sub("", title)
    title = re.sub(r"^\[(?:coordinators?|coordinator|[^\]]+)\]\s*", "", title, flags=re.IGNORECASE)
    return clean_text(title)


def entry_team(node, fallback: str | None = None) -> str | None:
    """Extract a bracketed team label or the organization heading from old pages."""
    match = TEAM_RE.match(clean_text(node.get_text(" ", strip=True)))
    if match and match.group(1).lower() not in {"coordinator", "coordinators"}:
        return match.group(1).strip()
    return fallback


def entry_authors(node, title: str, sibling=None) -> list[str]:
    """Extract simple author lines without treating affiliations as paper titles."""
    source = sibling if sibling is not None else node
    authors: list[str] = []
    for line in split_lines(source):
        if line == title or PAGE_RE.fullmatch(line) or "file" in line.lower():
            continue
        if line.startswith("["):
            continue
        if line not in authors:
            authors.append(line)
    return authors


def parse_entry(node, base_url: str, organization: str | None = None) -> dict | None:
    """Parse one ``dt``, ``dd``, or ``li`` paper entry."""
    source_format, source_url = choose_source_link(node, base_url)
    if source_url is None:
        return None
    title = entry_title(node)
    if not title:
        return None
    author_sibling = node.find_next_sibling("dd") if node.name == "dt" else None
    authors = entry_authors(node, title, author_sibling)
    raw_text = clean_text(node.get_text(" ", strip=True))
    is_overview = bool(
        re.search(r"\[coordinators?\]", raw_text, re.IGNORECASE)
        or OVERVIEW_RE.search(title)
        or "overview" in source_url.casefold()
    )
    return {
        "source_id": Path(urlparse(source_url).path).name,
        "source_url": source_url,
        "pdf_url": source_url if source_format == "pdf" else None,
        "source_format": source_format,
        "title": title,
        "authors": authors,
        "team_name": entry_team(node, organization),
        "is_overview": is_overview,
    }


def _named_track_centers(soup) -> list:
    """Return one legacy track header center per named track anchor."""
    centers = []
    seen: set[int] = set()
    for anchor in soup.find_all("a", attrs={"name": True}):
        center = anchor.find_parent("center")
        if center is None or id(center) in seen:
            continue
        label = center.find("b")
        if label is None or not clean_text(label.get_text(" ", strip=True)):
            continue
        seen.add(id(center))
        centers.append(center)
    return centers


def _legacy_track_name(center) -> str:
    label = center.find("b")
    return clean_text(label.get_text(" ", strip=True)) if label is not None else "Unknown Track"


def _legacy_entries(center, next_center, base_url: str) -> list[dict]:
    """Parse paper entries between two old-style track centers."""
    entries: list[dict] = []
    current_organization = None
    for sibling in center.next_siblings:
        if sibling is next_center:
            break
        if not getattr(sibling, "name", None):
            continue
        if sibling.name == "li":
            parsed = parse_entry(sibling, base_url)
            if parsed:
                entries.append(parsed)
            continue
        if sibling.name != "dl":
            continue
        for child in sibling.find_all(recursive=False):
            if child.name == "dt":
                current_organization = clean_text(child.get_text(" ", strip=True))
            elif child.name == "dd":
                parsed = parse_entry(child, base_url, current_organization)
                if parsed:
                    entries.append(parsed)
    return entries


def _modern_track_headers(soup) -> list:
    """Find modern heading elements whose child anchor names a track."""
    headers = []
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading.find("a", attrs={"name": True}) is not None:
            headers.append(heading)
    return headers


def _modern_entries(heading, next_heading, base_url: str) -> list[dict]:
    entries: list[dict] = []
    for element in heading.find_all_next(["h1", "h2", "h3", "h4", "h5", "h6", "dt", "li"]):
        if element is next_heading:
            break
        if element.name not in {"dt", "li"}:
            continue
        parsed = parse_entry(element, base_url)
        if parsed:
            entries.append(parsed)
    return entries


def parse_track_page(raw_html: str, base_url: str) -> list[dict]:
    """Parse official NIST track sections across modern and legacy layouts."""
    soup = BeautifulSoup(raw_html, "lxml")
    modern_headers = _modern_track_headers(soup)
    if modern_headers:
        sections = []
        for index, heading in enumerate(modern_headers):
            next_heading = modern_headers[index + 1] if index + 1 < len(modern_headers) else None
            track_name = clean_text(heading.get_text(" ", strip=True))
            entries = _modern_entries(heading, next_heading, base_url)
            sections.append({"track_name": track_name, "papers": entries})
        return deduplicate_sections(sections)

    centers = _named_track_centers(soup)
    sections = []
    for index, center in enumerate(centers):
        next_center = centers[index + 1] if index + 1 < len(centers) else None
        sections.append({
            "track_name": _legacy_track_name(center),
            "papers": _legacy_entries(center, next_center, base_url),
        })
    if centers and not any(section["papers"] for section in sections):
        sections = _parse_malformed_legacy_sections(raw_html, base_url, centers)
    return deduplicate_sections(sections)


def _source_format(source_url: str) -> str | None:
    """Return the supported source format for one official paper URL."""
    path = urlparse(source_url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith(".ps"):
        return "postscript"
    if path.endswith(".gz"):
        return "compressed"
    if path.endswith(".txt"):
        return "text"
    return None


def _raw_legacy_entries(section_html: str, base_url: str) -> list[dict]:
    """Recover entries from malformed early NIST HTML with unclosed ``dt`` tags."""
    matches = list(SOURCE_ANCHOR_RE.finditer(section_html))
    entries: list[dict] = []
    seen_urls: set[str] = set()
    for index, match in enumerate(matches):
        source_url = urljoin(base_url, match.group("href"))
        source_format = _source_format(source_url)
        if source_format is None or source_url in seen_urls:
            continue
        next_anchor = matches[index + 1].start() if index + 1 < len(matches) else len(section_html)
        tail = section_html[match.end():next_anchor]
        title_html = re.split(r"<br\b[^>]*>", tail, maxsplit=1, flags=re.IGNORECASE)[0]
        title = clean_text(BeautifulSoup(title_html, "lxml").get_text(" ", strip=True))
        title = PAGE_RE.sub("", title)
        if not title:
            continue
        prefix = section_html[:match.start()]
        organizations = re.findall(
            r"<dt\b[^>]*>\s*<b\b[^>]*>(.*?)</b>",
            prefix,
            flags=re.IGNORECASE | re.DOTALL,
        )
        organization = clean_text(BeautifulSoup(organizations[-1], "lxml").get_text(" ", strip=True)) if organizations else None
        seen_urls.add(source_url)
        entries.append({
            "source_id": Path(urlparse(source_url).path).name,
            "source_url": source_url,
            "pdf_url": source_url if source_format == "pdf" else None,
            "source_format": source_format,
            "title": title,
            "authors": [],
            "team_name": organization,
            "is_overview": bool(OVERVIEW_RE.search(title) or "overview" in source_url.lower()),
        })
    return entries


def _parse_malformed_legacy_sections(raw_html: str, base_url: str, centers: list) -> list[dict]:
    """Parse early track indexes whose invalid HTML defeats tree-based ``dt`` parsing."""
    sections: list[dict] = []
    cursor = 0
    for center_index, center in enumerate(centers):
        anchor = center.find("a", attrs={"name": True})
        if anchor is None:
            continue
        name = anchor.get("name", "")
        pattern = re.compile(
            rf"<a\b[^>]*\bname\s*=\s*['\"]{re.escape(name)}['\"][^>]*>",
            re.IGNORECASE,
        )
        start_match = pattern.search(raw_html, cursor)
        if start_match is None:
            continue
        cursor = start_match.end()
        next_start = len(raw_html)
        for next_center in centers[center_index + 1:]:
            next_anchor = next_center.find("a", attrs={"name": True})
            if next_anchor is None:
                continue
            next_name = next_anchor.get("name", "")
            next_pattern = re.compile(
                rf"<a\b[^>]*\bname\s*=\s*['\"]{re.escape(next_name)}['\"][^>]*>",
                re.IGNORECASE,
            )
            next_match = next_pattern.search(raw_html, cursor)
            if next_match is not None:
                next_start = next_match.start()
            break
        sections.append({
            "track_name": _legacy_track_name(center),
            "papers": _raw_legacy_entries(raw_html[cursor:next_start], base_url),
        })
        cursor = next_start
    return sections


def deduplicate_sections(sections: list[dict]) -> list[dict]:
    """Collapse duplicate navigation/content sections emitted by old NIST pages."""
    unique: dict[str, dict] = {}
    order: list[str] = []
    for section in sections:
        key = clean_text(section["track_name"]).casefold()
        previous = unique.get(key)
        if previous is None:
            unique[key] = section
            order.append(key)
        elif len(section["papers"]) > len(previous["papers"]):
            unique[key] = section
    return [unique[key] for key in order]


def parse_overview_index(raw_html: str, base_url: str) -> list[dict]:
    """Parse official overview papers listed separately on a proceedings page."""
    soup = BeautifulSoup(raw_html, "lxml")
    heading = next(
        (
            heading
            for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            if "overview papers" in clean_text(heading.get_text(" ", strip=True)).casefold()
        ),
        None,
    )
    if heading is None:
        return []
    overview_nodes: list = []
    ordered_list = heading.find_next("ol")
    if ordered_list is not None:
        overview_nodes.extend(ordered_list.find_all("li"))
    else:
        parent = heading.find_parent("td") or heading.parent
        after_heading = False
        for element in parent.find_all(recursive=False):
            if element is heading:
                after_heading = True
                continue
            if after_heading and element.name == "li":
                overview_nodes.append(element)

    entries: list[dict] = []
    seen_urls: set[str] = set()
    for element in overview_nodes:
        parsed = parse_entry(element, base_url)
        if parsed is None or parsed["source_url"] in seen_urls:
            continue
        seen_urls.add(parsed["source_url"])
        entries.append(parsed)
    return entries


def attach_overview_papers(sections: list[dict], overview_entries: list[dict]) -> list[dict]:
    """Attach proceedings-page overviews to track sections lacking one."""
    for section in sections:
        if any(paper["is_overview"] for paper in section["papers"]):
            continue
        track_name = normalize_title(section["track_name"])
        matches = [
            paper
            for paper in overview_entries
            if track_name and track_name in normalize_title(paper["title"])
        ]
        if len(matches) == 1:
            section["papers"].insert(0, {**matches[0], "is_overview": True})
    return sections


def normalize_title(title: str) -> str:
    """Normalize titles for non-authoritative DBLP matching."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def parse_dblp_titles(raw_html: str) -> set[str]:
    """Extract normalized DBLP titles, returning empty for challenge/empty pages."""
    soup = BeautifulSoup(raw_html, "lxml")
    titles = set()
    for entry in soup.select("li.entry.inproceedings"):
        title_span = entry.find("span", class_="title")
        if title_span is not None:
            titles.add(normalize_title(title_span.get_text(" ", strip=True).rstrip(".")))
    return titles


def parse_tira_refs(raw_html: str, year: int, track_name: str) -> list[str]:
    """Find supplemental public TIRA task links mentioning this TREC track."""
    soup = BeautifulSoup(raw_html, "lxml")
    refs = []
    track_tokens = set(normalize_title(track_name).split()) - {"track"}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = normalize_title(anchor.get_text(" ", strip=True) + " " + href)
        if "task overview" not in text and "task-overview" not in href.lower():
            continue
        if str(year) in text and track_tokens.intersection(text.split()):
            refs.append(urljoin("https://www.tira.io", href))
    return sorted(set(refs))


def paper_record(paper: dict, track_name: str, tira_refs: list[str]) -> dict:
    """Convert a parsed NIST paper to the common participant/overview shape."""
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": paper["pdf_url"],
        "team_name": paper["team_name"],
        "code_urls": [],
        "tira_refs": tira_refs,
        "source_id": paper["source_id"],
        "paper_url": paper["source_url"],
        "source_format": paper["source_format"],
        "track_name": track_name,
    }


def build_task_candidate(
    section: dict,
    edition: dict,
    duplicated_participant_urls: set[str],
    dblp_titles: set[str],
    tira_refs: list[str],
    logger: logging.Logger,
) -> dict | None:
    """Build and screen one official NIST track section."""
    papers = section["papers"]
    if not papers:
        return None
    overviews = [paper for paper in papers if paper["is_overview"]]
    overview = overviews[0] if overviews else None
    all_participants = [paper for paper in papers if paper not in overviews]
    unambiguous = [paper for paper in all_participants if paper["source_url"] not in duplicated_participant_urls]
    excluded_shared = len(all_participants) - len(unambiguous)
    reasons: list[str] = []
    if len(overviews) != 1:
        reasons.append(f"expected exactly one official overview, found {len(overviews)}")
    if overview is None:
        # Keep the unresolved grouping in the source review report, but do not make a
        # malformed candidate that can accidentally reach the document stages.
        logger.warning("TREC %s %s: no official overview marker", edition["year"], section["track_name"])
        return {
            "record_type": "unresolved_trec_track",
            "venue": "TREC",
            "year": edition["year"],
            "track_name": section["track_name"],
            "decision": "review",
            "reason": "official track section has no recognizable overview paper",
            "papers": papers,
        }
    if len(unambiguous) < 2:
        reasons.append(f"found only {len(unambiguous)} unambiguous participant papers")
    if overview["pdf_url"] is None:
        reasons.append(f"overview is only available as {overview['source_format']}")
    if any(paper["pdf_url"] is None for paper in unambiguous):
        reasons.append("at least one participant is not available as an official PDF")
    if excluded_shared:
        reasons.append(f"excluded {excluded_shared} participant paper(s) listed under multiple tracks")
    participant_urls = [paper["pdf_url"] for paper in unambiguous if paper["pdf_url"]]
    if len(participant_urls) != len(set(participant_urls)):
        reasons.append("duplicate participant PDF URL")
    if normalize_title(overview["title"]) not in dblp_titles and dblp_titles:
        logger.info("TREC %s %s: overview not found in DBLP title cache", edition["year"], section["track_name"])

    task_name = section["track_name"]
    task_id = f"trec{edition['year']}-{slugify(task_name)}"
    confidence = "high" if not reasons else "medium"
    decision = "include" if confidence == "high" else "review"
    candidate = {
        "task_id": task_id,
        "venue": task_name,
        "parent_venue": "TREC",
        "year": edition["year"],
        "task_name": task_name,
        "ceur_volume": None,
        "source": {
            "provider": "nist_trec",
            "collection_id": edition["collection_id"],
            "proceedings_url": edition["proceedings_url"],
            "track_url": edition.get("track_url"),
            "dblp_url": dblp_url(edition["year"]),
            "tira_refs": tira_refs,
        },
        "overview": {
            **paper_record(overview, task_name, tira_refs),
            "is_umbrella": False,
        },
        "participants": [paper_record(paper, task_name, tira_refs) for paper in unambiguous],
        "counts": {
            "notebook_papers": len(unambiguous),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": "official_track_section",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
            "dblp_overview_match": bool(dblp_titles and normalize_title(overview["title"]) in dblp_titles),
            "tira_track_matches": tira_refs,
        },
        "screening": {
            "decision": decision,
            "checks": {
                "one_overview": len(overviews) == 1,
                "official_track_section": True,
                "minimum_participants": len(unambiguous) >= 2,
                "official_pdf_links": overview["pdf_url"] is not None and all(
                    paper["pdf_url"] is not None for paper in unambiguous
                ),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
                "no_multi_track_participants": excluded_shared == 0,
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers; confidence=%s)",
        task_id, decision, len(unambiguous), confidence,
    )
    return candidate


def collect_edition(edition: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect candidates from one cached TREC edition."""
    edition_dir = RAW_DIR / "years" / edition["collection_id"]
    track_path = edition_dir / "tracks.html"
    proceedings_path = edition_dir / "proceedings.html"
    if not proceedings_path.exists() and not track_path.exists():
        raise FileNotFoundError(f"missing cached TREC proceedings: {proceedings_path}")
    proceedings_html = proceedings_path.read_text(encoding="utf-8") if proceedings_path.exists() else ""
    track_url = discover_track_url(proceedings_html, edition["proceedings_url"]) if proceedings_html else None
    source_path = track_path if track_path.exists() else proceedings_path
    source_html = source_path.read_text(encoding="utf-8")
    sections = parse_track_page(source_html, track_url or edition["proceedings_url"])
    sections = attach_overview_papers(
        sections,
        parse_overview_index(proceedings_html, edition["proceedings_url"]) if proceedings_html else [],
    )
    edition = {**edition, "track_url": track_url}
    if not sections:
        review = [{
            "record_type": "unresolved_trec_edition",
            "venue": "TREC",
            "year": edition["year"],
            "decision": "review",
            "reason": "no track sections could be parsed from the cached NIST page",
            "source": edition,
        }]
        return [], review, []

    dblp_path = RAW_DIR / "dblp" / f"{edition['collection_id']}.html"
    dblp_titles = parse_dblp_titles(dblp_path.read_text(encoding="utf-8")) if dblp_path.exists() else set()
    tira_path = RAW_DIR / "tira-tasks.html"
    tira_html = tira_path.read_text(encoding="utf-8") if tira_path.exists() else ""
    occurrences: defaultdict[str, set[str]] = defaultdict(set)
    for section in sections:
        for paper in section["papers"]:
            if paper["is_overview"]:
                continue
            occurrences[paper["source_url"]].add(section["track_name"])
    duplicated = {url for url, tracks in occurrences.items() if len(tracks) > 1}
    candidates: list[dict] = []
    review: list[dict] = []
    for section in sections:
        tira_refs = parse_tira_refs(tira_html, edition["year"], section["track_name"])
        record = build_task_candidate(section, edition, duplicated, dblp_titles, tira_refs, logger)
        if record is None:
            continue
        if "task_id" not in record:
            review.append(record)
        else:
            candidates.append(record)
            if record["provenance"]["confidence"] != "high":
                review.append(record)
    logger.info(
        "TREC %s: parsed %d track sections, %d candidates, %d unresolved records",
        edition["year"], len(sections), len(candidates), len(review),
    )
    return candidates, review, []


def write_screening_report(candidates: list[dict], review: list[dict], excluded: list[dict], path: Path) -> None:
    """Write a compact, generated report for automatic TREC screening."""
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# TREC screening report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate task groups: {len(candidates)}",
        f"High-confidence tasks: {len(high)}",
        f"Tasks/records needing review: {len(review)}",
        f"Excluded records: {len(excluded)}",
        "",
        "## High-confidence tasks",
        "",
    ]
    lines.extend(
        f"- `{c['task_id']}` — {len(c['participants'])} participants — overview: {c['overview']['paper_url']}"
        for c in high
    )
    lines += ["", "## Review records", ""]
    for record in review:
        if "task_id" in record:
            reasons = "; ".join(record["provenance"].get("confidence_reasons", [])) or "unspecified"
            lines.append(f"- `{record['task_id']}` — {reasons}")
        else:
            lines.append(
                f"- TREC {record.get('year')} {record.get('track_name', 'edition')} — {record.get('reason', 'review')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger) -> bool:
    """Process all selected cached TREC editions and write source outputs."""
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured TREC edition for year %s", year)
        return False
    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    try:
        for edition in editions:
            edition_candidates, edition_review, edition_excluded = collect_edition(edition, logger)
            candidates.extend(edition_candidates)
            review.extend(edition_review)
            excluded.extend(edition_excluded)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("TREC collection failed: %s", exc)
        return False

    candidates.sort(key=lambda candidate: candidate["task_id"])
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, CANDIDATES_DIR / "trec.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "trec.jsonl")
    write_jsonl(review, SCREENING_DIR / "trec_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "trec_excluded.jsonl")
    write_screening_report(candidates, review, excluded, SCREENING_DIR / "trec_report.md")
    logger.info(
        "wrote %d TREC candidates (%d high, %d review) to %s",
        len(candidates), sum(1 for c in candidates if c["provenance"]["confidence"] == "high"),
        len(review), CANDIDATES_DIR / "trec.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and screen TREC task candidates from cached NIST proceedings.")
    parser.add_argument("--year", type=int, help="Collect only one configured TREC year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_trec")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
