#!/usr/bin/env python
"""Collect high-precision MediaEval task candidates from official proceedings."""

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
from src.mediaeval_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "mediaeval"
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "intermediate"
CANDIDATES_DIR = INTERMEDIATE_DIR / "candidates"
SCREENING_DIR = INTERMEDIATE_DIR / "screening"
LOGS_DIR = PROJECT_ROOT / "logs"

PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
OVERVIEW_LABEL_RE = re.compile(r"\boverview\s+papers?\b", re.IGNORECASE)
WORKING_NOTES_LABEL_RE = re.compile(r"\bworking\s+notes\s+papers?\b", re.IGNORECASE)
Q4I_LABEL_RE = re.compile(r"\bquest\s+for\s+insight\s+papers?\b", re.IGNORECASE)
MULTI_TASK_TITLE_RE = re.compile(
    r"\b(?:task|tasks|track|tracks|challenge|challenges)\b.*\band\b.*"
    r"\b(?:task|tasks|track|tracks|challenge|challenges)\b",
    re.IGNORECASE,
)
OVERVIEW_TITLE_RE = re.compile(
    r"\b(?:overview|challenges?,?\s+dataset\s+and\s+evaluation|task\s+overview)\b",
    re.IGNORECASE,
)
EXCLUDED_SECTION_RE = re.compile(
    r"\b(?:preface|program(?:me)?\s+committee|table\s+of\s+contents|author\s+index|"
    r"mediaeval\s+letters?|brave\s+new\s+tasks|working\s+notes\s+proceedings)\b",
    re.IGNORECASE,
)
EXCLUDED_PAPER_RE = re.compile(
    r"\b(?:preface|program(?:me)?\s+committee|table\s+of\s+contents|author\s+index)\b",
    re.IGNORECASE,
)
TEAM_MARKER_RE = re.compile(r"^(.+?)\s+(?:at|@|in)\s+mediaeval\b", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "at", "for", "from", "in", "of", "on", "or", "the", "to",
    "task", "tasks", "mediaeval", "multimedia", "benchmark", "workshop", "overview",
    "working", "notes", "paper", "papers", "proceedings", "challenge", "challenges",
    "dataset", "datasets", "evaluation", "using", "based", "with", "without", "team",
}


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_mediaeval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Collapse HTML whitespace while preserving title punctuation."""
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(title: str) -> str:
    """Normalize a title for supplemental DBLP matching."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def parse_dblp_titles(raw_html: str) -> set[str]:
    """Extract normalized DBLP titles without allowing DBLP to create records."""
    soup = BeautifulSoup(raw_html, "lxml")
    titles: set[str] = set()
    for entry in soup.select("li.entry.inproceedings"):
        node = entry.find("span", class_="title")
        if node is not None:
            titles.add(normalize_title(node.get_text(" ", strip=True).rstrip(".")))
    return titles


def parse_tira_refs(raw_html: str, year: int, task_name: str) -> list[str]:
    """Find supplemental TIRA task links mentioning this MediaEval task."""
    soup = BeautifulSoup(raw_html, "lxml")
    task_tokens = set(normalize_title(task_name).split()) - STOPWORDS
    refs: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        text = normalize_title(anchor.get_text(" ", strip=True) + " " + href)
        if str(year) not in text or not task_tokens:
            continue
        if not task_tokens.intersection(text.split()):
            continue
        if not any(marker in href.casefold() for marker in ("task", "mediaeval", "shared")):
            continue
        refs.add(urljoin("https://www.tira.io", href))
    return sorted(refs)


def _heading_level(node) -> int:
    match = re.fullmatch(r"h([1-6])", node.name or "")
    return int(match.group(1)) if match else 99


def _role_from_label(text: str) -> str | None:
    if OVERVIEW_LABEL_RE.search(text):
        return "overview"
    if WORKING_NOTES_LABEL_RE.search(text):
        return "working_notes"
    if Q4I_LABEL_RE.search(text):
        return "quest_for_insight"
    return None


def _is_umbrella_title(title: str) -> bool:
    """Detect an organizer title that explicitly covers multiple task units."""
    return bool(MULTI_TASK_TITLE_RE.search(title))


def _extract_papers(list_node, base_url: str, role: str, role_label: str) -> list[dict]:
    papers = []
    for position, item in enumerate(list_node.find_all("li", recursive=False), start=1):
        title_node = item.find("span", class_="CEURTITLE")
        anchor = item.find("a", href=True)
        if title_node is None or anchor is None or not PDF_RE.search(anchor.get("href", "")):
            continue
        title = clean_text(title_node.get_text(" ", strip=True))
        authors = []
        for author_node in item.find_all("span", class_=re.compile(r"^CEURAUTHORS?$")):
            authors.extend(
                author.strip()
                for author in author_node.get_text(" ", strip=True).split(",")
                if author.strip()
            )
        papers.append({
            "title": title,
            "authors": authors,
            "pdf_url": urljoin(base_url, anchor["href"]),
            "position_in_section": position,
            "role": role,
            "role_label": role_label,
        })
    return papers


def parse_ceur_mediaeval(raw_html: str, volume: str) -> list[dict]:
    """Parse CEUR task headings and their explicit paper-role subsections.

    MediaEval CEUR pages put the overview and working-notes lists below
    separate headings, unlike the single-list layout used by FIRE.  The
    ``CEURSESSION`` heading identifies a task; nested headings without that
    marker are containers and do not create records.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    base_url = f"https://ceur-ws.org/Vol-{volume}/"
    all_headings = soup.find_all(re.compile(r"^h[1-6]$"))
    task_headings = [
        heading for heading in all_headings
        if heading.find("span", class_="CEURSESSION") is not None
    ]
    sections = []
    for index, task_heading in enumerate(task_headings):
        session = task_heading.find("span", class_="CEURSESSION")
        track_name = clean_text(session.get_text(" ", strip=True))
        if not track_name or EXCLUDED_SECTION_RE.search(track_name):
            continue
        next_task = task_headings[index + 1] if index + 1 < len(task_headings) else None
        role_papers: list[dict] = []
        start_index = all_headings.index(task_heading)
        end_index = all_headings.index(next_task) if next_task is not None else len(all_headings)
        role_headings = []
        for cursor in all_headings[start_index + 1 : end_index]:
            role = _role_from_label(clean_text(cursor.get_text(" ", strip=True)))
            if role is not None:
                role_headings.append((cursor, role, clean_text(cursor.get_text(" ", strip=True))))
        for role_index, (role_heading, role, role_label) in enumerate(role_headings):
            next_role = role_headings[role_index + 1][0] if role_index + 1 < len(role_headings) else next_task
            sibling = role_heading.find_next_sibling()
            while sibling is not None and sibling is not next_role:
                if getattr(sibling, "name", None) == "ul":
                    role_papers.extend(_extract_papers(sibling, base_url, role, role_label))
                    break
                if getattr(sibling, "name", None) and re.fullmatch(r"h[1-6]", sibling.name):
                    break
                sibling = sibling.find_next_sibling()
        if not role_papers:
            # Preserve unlabeled lists for review rather than silently losing
            # papers from older or malformed CEUR pages.
            sibling = task_heading.find_next_sibling()
            while sibling is not None and sibling is not next_task:
                if getattr(sibling, "name", None) == "ul":
                    role_papers.extend(_extract_papers(sibling, base_url, "unknown", ""))
                sibling = sibling.find_next_sibling()
        sections.append({"lab_name": track_name, "papers": role_papers})
    return sections


def parse_legacy_ceur_mediaeval(raw_html: str, volume: str) -> list[dict]:
    """Parse early CEUR MediaEval pages without ``CEURSESSION`` markers.

    MediaEval 2011 and 2012 expose the same explicit overview/working-notes
    headings as later volumes, but identify tasks with ordinary ``h2``/``h3``
    headings.  A task is emitted only when a role heading occurs in its heading
    boundary; unrelated proceedings front matter is ignored.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    base_url = f"https://ceur-ws.org/Vol-{volume}/"
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    sections = []
    for index, task_heading in enumerate(headings):
        if task_heading.name not in {"h2", "h3"}:
            continue
        track_name = clean_text(task_heading.get_text(" ", strip=True))
        if not track_name or EXCLUDED_SECTION_RE.search(track_name):
            continue
        task_level = _heading_level(task_heading)
        end_index = len(headings)
        for next_index in range(index + 1, len(headings)):
            if _heading_level(headings[next_index]) <= task_level:
                end_index = next_index
                break
        role_headings = []
        for role_heading in headings[index + 1 : end_index]:
            role = _role_from_label(clean_text(role_heading.get_text(" ", strip=True)))
            if role is not None:
                role_headings.append((role_heading, role, clean_text(role_heading.get_text(" ", strip=True))))
        if not role_headings:
            continue
        papers = []
        for role_index, (role_heading, role, role_label) in enumerate(role_headings):
            next_role = role_headings[role_index + 1][0] if role_index + 1 < len(role_headings) else None
            sibling = role_heading.find_next_sibling()
            while sibling is not None and sibling is not next_role:
                if getattr(sibling, "name", None) == "ul":
                    papers.extend(_extract_papers(sibling, base_url, role, role_label))
                    break
                if getattr(sibling, "name", None) and re.fullmatch(r"h[1-6]", sibling.name):
                    break
                sibling = sibling.find_next_sibling()
        if papers:
            sections.append({"lab_name": track_name, "papers": papers})
    return sections


def _legacy_track_name(soup: BeautifulSoup, source_url: str) -> str:
    year_match = re.search(r"20\d{2}", source_url)
    year = year_match.group(0) if year_match else ""
    headings = soup.find_all(re.compile(r"^h[1-3]$"))
    for heading in reversed(headings):
        text = clean_text(heading.get_text(" ", strip=True))
        if not text or EXCLUDED_SECTION_RE.search(text):
            continue
        if year and year in text:
            return text
        if re.search(r"\b(?:task|challenge|track)\b", text, re.IGNORECASE):
            return text
    path_parts = [part for part in urlparse(source_url).path.split("/") if part]
    return clean_text(path_parts[-1].replace("-", " ").replace("_", " ")) or "MediaEval legacy task"


def parse_legacy_mediaeval_page(raw_html: str, source_url: str) -> list[dict]:
    """Extract legacy task-page PDF links, keeping title inference review-only."""
    soup = BeautifulSoup(raw_html, "lxml")
    track_name = _legacy_track_name(soup, source_url)
    papers = []
    for position, anchor in enumerate(soup.find_all("a", href=True), start=1):
        href = anchor.get("href", "").strip()
        if not PDF_RE.search(href):
            continue
        pdf_url = urljoin(source_url, href)
        parsed_pdf = urlparse(pdf_url)
        if "worknotes" not in parsed_pdf.path.casefold() and "multimediaeval.org" not in parsed_pdf.netloc.casefold():
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            continue
        papers.append({
            "title": title,
            "authors": [],
            "pdf_url": pdf_url,
            "position_in_section": position,
            "role": "overview" if OVERVIEW_TITLE_RE.search(title) else "unknown",
            "role_label": "title-inferred",
        })
    return [{"lab_name": track_name, "papers": papers}] if papers else []


def tokenize(title: str) -> set[str]:
    """Return discriminative title tokens for diagnostics and legacy matching."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title.lower()))
    return {
        word for word in words
        if word not in STOPWORDS and len(word) > 2 and not re.fullmatch(r"20\d{2}", word)
    }


def infer_team_name(title: str) -> str | None:
    match = TEAM_MARKER_RE.search(title)
    return match.group(1).strip(" :-–—") if match else None


def paper_record(paper: dict, track_name: str, collection_id: str, tira_refs: list[str]) -> dict:
    pdf_url = paper["pdf_url"]
    return {
        "title": paper["title"],
        "authors": paper.get("authors", []),
        "pdf_url": pdf_url,
        "team_name": infer_team_name(paper["title"]),
        "code_urls": [],
        "tira_refs": tira_refs,
        "source_id": Path(urlparse(pdf_url).path).name,
        "paper_url": pdf_url,
        "source_format": "pdf",
        "track_name": track_name,
        "source_collection_id": collection_id,
        "paper_type": paper.get("role", "unknown"),
    }


def _prepare_papers(section: dict) -> list[dict]:
    papers = []
    for paper in section.get("papers", []):
        title = clean_text(paper.get("title", ""))
        if not title or EXCLUDED_PAPER_RE.search(title) or not paper.get("pdf_url"):
            continue
        papers.append({**paper, "title": title})
    return papers


def combine_umbrella_sections(sections: list[dict]) -> list[dict]:
    """Combine sections sharing one explicitly multi-task organizer overview.

    Early MediaEval proceedings reuse one overview PDF for two adjacent task
    headings. Keeping those headings separate would trigger the global duplicate
    document guard. Combining only titles that explicitly name multiple tasks
    preserves the one-overview/several-subtasks relationship without merging
    unrelated tracks by URL coincidence.
    """
    combined: list[dict] = []
    by_overview: dict[str, dict] = {}
    for section in sections:
        overview_papers = [
            paper for paper in section.get("papers", []) if paper.get("role") == "overview"
        ]
        overview_url = overview_papers[0].get("pdf_url") if len(overview_papers) == 1 else None
        if overview_url and _is_umbrella_title(overview_papers[0].get("title", "")):
            existing = by_overview.get(overview_url)
            if existing is None:
                existing = {
                    "lab_name": section["lab_name"],
                    "papers": list(section.get("papers", [])),
                    "is_umbrella": True,
                }
                by_overview[overview_url] = existing
                combined.append(existing)
            else:
                existing["lab_name"] = f"{existing['lab_name']} + {section['lab_name']}"
                known_urls = {paper.get("pdf_url") for paper in existing["papers"]}
                existing["papers"].extend(
                    paper for paper in section.get("papers", [])
                    if paper.get("pdf_url") not in known_urls
                )
            continue
        combined.append(section)
    return combined


def build_task_candidate(
    section: dict,
    edition: dict,
    papers: list[dict],
    duplicated_participant_urls: set[str],
    dblp_titles: set[str],
    tira_refs: list[str],
    logger: logging.Logger,
    occurrence: int = 1,
) -> dict:
    """Build a candidate and automatically demote ambiguous assignments."""
    track_name = section["lab_name"]
    explicit_overviews = [paper for paper in papers if paper.get("role") == "overview"]
    participants = [
        paper for paper in papers
        if paper.get("role") in {"working_notes", "quest_for_insight"}
    ]
    unknown = [paper for paper in papers if paper.get("role") == "unknown"]
    title_overviews = [paper for paper in unknown if OVERVIEW_TITLE_RE.search(paper["title"])]
    overviews = explicit_overviews or title_overviews
    reasons: list[str] = []
    if not explicit_overviews:
        reasons.append("overview inferred from title or unlabeled legacy page")
    if len(overviews) != 1:
        reasons.append(f"found {len(overviews)} organizer overview papers")
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} participant papers")
    if unknown:
        reasons.append(f"{len(unknown)} paper(s) have no explicit participant role")
    if edition.get("ceur_volume") is None:
        reasons.append("legacy official page grouping requires review")
    participant_urls = [paper["pdf_url"] for paper in participants]
    if len(participant_urls) != len(set(participant_urls)):
        reasons.append("duplicate participant PDF URL")
    shared = [paper for paper in participants if paper["pdf_url"] in duplicated_participant_urls]
    if shared:
        reasons.append(f"{len(shared)} participant paper(s) also occur in another task section")

    overview = overviews[0] if len(overviews) == 1 else (overviews[0] if overviews else papers[0])
    task_name = track_name
    task_id = f"mediaeval{edition['year']}-{slugify(task_name)}"
    if occurrence > 1:
        task_id = f"{task_id}-{occurrence}"
    confidence = "high" if not reasons else "medium"
    candidate = {
        "task_id": task_id,
        "venue": task_name,
        "parent_venue": "MediaEval",
        "year": edition["year"],
        "task_name": task_name,
        "ceur_volume": edition.get("ceur_volume"),
        "source": {
            "provider": "ceur_mediaeval" if edition.get("ceur_volume") else "mediaeval_archive",
            "collection_id": edition["collection_id"],
            "proceedings_url": edition["proceedings_url"],
            "official_url": edition["official_url"],
            "track_name": track_name,
            "dblp_url": edition.get("dblp_url"),
            "tira_refs": tira_refs,
        },
        "overview": {
            **paper_record(overview, track_name, edition["collection_id"], tira_refs),
            "is_umbrella": bool(section.get("is_umbrella")) or _is_umbrella_title(overview["title"]),
        },
        "participants": [
            paper_record(paper, track_name, edition["collection_id"], tira_refs)
            for paper in participants
        ],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": (
                "umbrella_role_section_grouping"
                if section.get("is_umbrella")
                else "role_section_grouping" if explicit_overviews else "legacy_title_inference"
            ),
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
            "dblp_overview_match": bool(dblp_titles and normalize_title(overview["title"]) in dblp_titles),
            "tira_track_matches": tira_refs,
        },
        "screening": {
            "decision": "include" if confidence == "high" else "review",
            "checks": {
                "one_overview": len(overviews) == 1,
                "official_track_section": bool(track_name),
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": bool(overview.get("pdf_url")) and all(participant_urls),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
                "no_multi_track_participants": not shared,
                "explicit_paper_roles": not unknown,
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers; confidence=%s)",
        task_id, candidate["screening"]["decision"], len(participants), confidence,
    )
    return candidate


def collect_edition(edition: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect candidates from one cached MediaEval edition."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    sections: list[dict] = []
    proceedings_path = edition_dir / "proceedings.html"
    if edition.get("ceur_volume") and proceedings_path.exists():
        sections = parse_ceur_mediaeval(
            proceedings_path.read_text(encoding="utf-8"), edition["ceur_volume"]
        )
        if not sections:
            sections = parse_legacy_ceur_mediaeval(
                proceedings_path.read_text(encoding="utf-8"), edition["ceur_volume"]
            )
    else:
        task_pages_path = edition_dir / "task_pages.json"
        task_pages = []
        if task_pages_path.exists():
            try:
                task_pages = json.loads(task_pages_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("invalid task page index: %s", task_pages_path)
        if task_pages:
            for task_page in task_pages:
                page_path = edition_dir / task_page["filename"]
                if not page_path.exists():
                    continue
                sections.extend(parse_legacy_mediaeval_page(
                    page_path.read_text(encoding="utf-8"), task_page["url"]
                ))
        else:
            official_path = edition_dir / "official.html"
            if official_path.exists():
                sections.extend(parse_legacy_mediaeval_page(
                    official_path.read_text(encoding="utf-8"), edition["official_url"]
                ))
    if not sections:
        return [], [{
            "record_type": "unresolved_mediaeval_edition",
            "venue": "MediaEval",
            "year": edition["year"],
            "collection_id": edition["collection_id"],
            "decision": "review",
            "reason": "no parseable official MediaEval task sections with PDF links",
            "source": edition,
        }], []

    dblp_path = RAW_DIR / "dblp" / f"{edition['collection_id']}.html"
    dblp_titles = parse_dblp_titles(dblp_path.read_text(encoding="utf-8")) if dblp_path.exists() else set()
    tira_path = RAW_DIR / "tira-tasks.html"
    tira_html = tira_path.read_text(encoding="utf-8") if tira_path.exists() else ""

    normalized_sections = []
    for section in sections:
        if EXCLUDED_SECTION_RE.search(section.get("lab_name", "")):
            continue
        papers = _prepare_papers(section)
        if papers:
            normalized_sections.append({"lab_name": clean_text(section["lab_name"]), "papers": papers})

    normalized_sections = combine_umbrella_sections(normalized_sections)

    occurrences: defaultdict[str, set[str]] = defaultdict(set)
    for section in normalized_sections:
        for paper in section["papers"]:
            if paper.get("role") in {"working_notes", "quest_for_insight"}:
                occurrences[paper["pdf_url"]].add(section["lab_name"])
    duplicated = {url for url, section_names in occurrences.items() if len(section_names) > 1}
    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    for section in normalized_sections:
        task_name = section["lab_name"]
        refs = parse_tira_refs(tira_html, edition["year"], task_name)
        occurrence = sum(1 for candidate in candidates if candidate["task_name"] == task_name) + 1
        candidate = build_task_candidate(
            section, edition, section["papers"], duplicated, dblp_titles, refs, logger, occurrence
        )
        candidates.append(candidate)
        if candidate["provenance"]["confidence"] != "high":
            review.append(candidate)
    logger.info(
        "MediaEval %s: parsed %d sections, %d candidates, %d review records",
        edition["year"], len(normalized_sections), len(candidates), len(review),
    )
    return candidates, review, excluded


def write_screening_report(candidates: list[dict], review: list[dict], excluded: list[dict], path: Path) -> None:
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# MediaEval screening report", "", f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate task groups: {len(candidates)}", f"High-confidence tasks: {len(high)}",
        f"Tasks/records needing review: {len(review)}", f"Excluded records: {len(excluded)}", "",
        "## High-confidence tasks", "",
    ]
    lines.extend(
        f"- `{candidate['task_id']}` — {len(candidate['participants'])} participants — "
        f"overview: {candidate['overview']['paper_url']}"
        for candidate in high
    )
    lines.extend(["", "## Review records", ""])
    for record in review:
        if "task_id" in record:
            reason = "; ".join(record.get("provenance", {}).get("confidence_reasons", []))
            lines.append(f"- `{record['task_id']}` — {reason or 'review'}")
        else:
            lines.append(f"- MediaEval {record.get('year')} {record.get('track_name', record.get('collection_id', 'unknown'))} — {record.get('reason', 'review')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger) -> bool:
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured MediaEval edition for year %s", year)
        return False
    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    for edition in editions:
        edition_candidates, edition_review, edition_excluded = collect_edition(edition, logger)
        candidates.extend(edition_candidates)
        review.extend(edition_review)
        excluded.extend(edition_excluded)
    candidates.sort(key=lambda candidate: candidate["task_id"])
    review.sort(key=lambda record: record.get("task_id", record.get("collection_id", "")))
    write_jsonl(candidates, CANDIDATES_DIR / "mediaeval.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "mediaeval.jsonl")
    write_jsonl(review, SCREENING_DIR / "mediaeval_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "mediaeval_excluded.jsonl")
    write_screening_report(candidates, review, excluded, SCREENING_DIR / "mediaeval_report.md")
    logger.info(
        "wrote %d MediaEval candidates (%d high, %d review) to %s",
        len(candidates), sum(1 for candidate in candidates if candidate["provenance"]["confidence"] == "high"),
        len(review), CANDIDATES_DIR / "mediaeval.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect and screen MediaEval task candidates from cached proceedings."
    )
    parser.add_argument("--year", type=int, help="Collect only one configured MediaEval year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_mediaeval")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
