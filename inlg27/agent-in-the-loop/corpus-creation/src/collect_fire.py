#!/usr/bin/env python
"""Collect high-precision FIRE task candidates from official proceedings.

CEUR-WS working-notes pages are the authoritative source for FIRE 2015 onward.
They expose explicit track sections, an organizer overview, and participant
working notes.  Older FIRE archive pages are scanned as well, but are only
eligible for inclusion when they expose the same complete evidence.
"""

from __future__ import annotations

import argparse
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
from src.fire_config import selected_editions
from src.parse_sections import parse_ceur_volume


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "fire"
LOGS_DIR = PROJECT_ROOT / "logs"

PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
OVERVIEW_RE = re.compile(
    r"\boverview\b|\btrack\s+(?:final\s+)?report\b|\btrack\s+overview\b|"
    r"\bshared\s+task\s+description\b|\bfindings\s+of\b|"
    r"\bkey\s+takeaways\s+from\b",
    re.IGNORECASE,
)
EXCLUDED_SECTION_RE = re.compile(
    r"^(?:preface|foreword|keynote|invited talk|organization|organizers?|"
    r"programme|program|schedule|author index|table of contents|front matter)$|"
    r"\b(?:preface|foreword|keynote|invited talk|author index|table of contents|"
    r"conference papers|doctoral consortium|industry track)\b",
    re.IGNORECASE,
)
EXCLUDED_PAPER_RE = re.compile(
    r"\b(?:preface|foreword|keynote|invited talk|author index|table of contents|"
    r"organization|organizers?)\b",
    re.IGNORECASE,
)
TEAM_MARKER_RE = re.compile(r"\s+(?:@|at)\s+(?:FIRE|[A-Z][A-Za-z-]+)\b", re.IGNORECASE)

STOPWORDS = {
    "a", "an", "and", "at", "based", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "using", "with", "overview", "track", "tracks",
    "task", "tasks", "shared", "working", "notes", "fire", "forum", "information",
    "retrieval", "evaluation", "system", "systems", "approach", "approaches",
    "language", "languages", "detection", "identification", "classification",
    "analysis", "recognition", "model", "models", "method", "methods",
}


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_fire_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Extract normalized DBLP titles; DBLP never creates a FIRE paper."""
    soup = BeautifulSoup(raw_html, "lxml")
    titles: set[str] = set()
    for entry in soup.select("li.entry.inproceedings"):
        title_node = entry.find("span", class_="title")
        if title_node is not None:
            titles.add(normalize_title(title_node.get_text(" ", strip=True).rstrip(".")))
    return titles


def parse_tira_refs(raw_html: str, year: int, task_name: str) -> list[str]:
    """Find supplemental TIRA task links that mention this FIRE task."""
    soup = BeautifulSoup(raw_html, "lxml")
    task_tokens = set(normalize_title(task_name).split()) - STOPWORDS
    refs: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = normalize_title(anchor.get_text(" ", strip=True) + " " + href)
        if "task overview" not in text and "task-overview" not in href.casefold():
            continue
        if str(year) not in text:
            continue
        if task_tokens and not task_tokens.intersection(text.split()):
            continue
        refs.add(urljoin("https://www.tira.io", href))
    return sorted(refs)


def tokenize(title: str) -> set[str]:
    """Return discriminative title tokens for multi-overview sections."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    words = re.findall(r"[a-z0-9]+", spaced.lower())
    return {
        word for word in words
        if word not in STOPWORDS and len(word) > 2 and not re.fullmatch(r"20\d{2}", word)
    }


def clean_task_name(overview_title: str, fallback: str) -> str:
    """Turn an organizer title into a stable display name for split sections."""
    title = clean_text(overview_title).rstrip(".")
    title = re.sub(r"^overview\s+of\s+(?:the\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^overview\s*[:\-]?\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+(?:at|in|for)\s+FIRE\s*[- ]?20\d{2}.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+FIRE\s*[- ]?20\d{2}.*$", "", title, flags=re.IGNORECASE)
    title = title.strip(" :-–—")
    return title or fallback


def infer_team_name(title: str) -> str | None:
    """Extract a common team marker from participant titles when present."""
    match = TEAM_MARKER_RE.search(title)
    if match is None:
        return None
    team = title[:match.start()].strip(" :-–—")
    return team or None


def paper_record(paper: dict, track_name: str, source_collection_id: str, tira_refs: list[str]) -> dict:
    """Convert a CEUR paper record to the shared candidate contract."""
    pdf_url = paper["pdf_url"]
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": pdf_url,
        "team_name": infer_team_name(paper["title"]),
        "code_urls": [],
        "tira_refs": tira_refs,
        "source_id": Path(urlparse(pdf_url).path).name,
        "paper_url": pdf_url,
        "source_format": "pdf",
        "track_name": track_name,
        "source_collection_id": source_collection_id,
    }


def parse_legacy_fire_page(raw_html: str, base_url: str) -> list[dict]:
    """Best-effort parser for pre-CEUR FIRE archive pages.

    Historical pages differ substantially.  We preserve only PDF links grouped
    under an explicit heading; weak or incomplete results are demoted by the
    normal screening rules rather than guessed into the final corpus.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    sections: dict[str, list[dict]] = defaultdict(list)
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not PDF_RE.search(href):
            continue
        heading = anchor.find_previous(re.compile(r"^h[1-6]$"))
        track_name = clean_text(heading.get_text(" ", strip=True)) if heading else "Unstructured FIRE archive"
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            parent = anchor.find_parent(["li", "p", "div"])
            title = clean_text(parent.get_text(" ", strip=True)) if parent else ""
        if not title:
            continue
        sections[track_name].append({
            "title": title,
            "authors": [],
            "pdf_url": urljoin(base_url, href),
        })
    return [{"lab_name": name, "papers": papers} for name, papers in sections.items()]


def prepare_papers(section: dict) -> list[dict]:
    """Remove proceedings front matter while retaining official section order."""
    papers = []
    for paper in section.get("papers", []):
        title = clean_text(paper.get("title", ""))
        if not title or EXCLUDED_PAPER_RE.search(title):
            continue
        if not paper.get("pdf_url"):
            continue
        papers.append({**paper, "title": title, "is_overview": bool(OVERVIEW_RE.search(title))})
    return papers


def assign_by_title(
    papers: list[dict], overviews: list[dict], logger: logging.Logger, section_name: str
) -> tuple[dict[int, list[dict]], list[dict]]:
    """Assign multi-overview participants only with a unique positive match."""
    overview_tokens = {id(paper): tokenize(paper["title"]) for paper in overviews}
    token_counts: dict[str, int] = defaultdict(int)
    for tokens in overview_tokens.values():
        for token in tokens:
            token_counts[token] += 1
    weights = {token: 1.0 / count for token, count in token_counts.items()}
    assignments = {id(paper): [] for paper in overviews}
    unresolved: list[dict] = []
    overview_ids = {id(paper) for paper in overviews}
    for paper in papers:
        if id(paper) in overview_ids:
            continue
        paper_tokens = tokenize(paper["title"])
        scores = {
            overview_id: sum(weights[token] for token in paper_tokens & tokens)
            for overview_id, tokens in overview_tokens.items()
        }
        best = max(scores.values(), default=0)
        winners = [overview_id for overview_id, score in scores.items() if score == best and score > 0]
        if len(winners) != 1:
            unresolved.append(paper)
            continue
        assignments[winners[0]].append(paper)
    if unresolved:
        logger.warning(
            "FIRE section %r: %d participant papers unresolved by title matching",
            section_name,
            len(unresolved),
        )
    return assignments, unresolved


def build_task_candidate(
    section: dict,
    edition: dict,
    overview: dict,
    participants: list[dict],
    all_overviews: list[dict],
    duplicated_participant_urls: set[str],
    unresolved: list[dict],
    dblp_titles: set[str],
    tira_refs: list[str],
    logger: logging.Logger,
) -> dict:
    """Build one FIRE candidate and automatically demote structural ambiguity."""
    track_name = section["lab_name"]
    reasons: list[str] = []
    if len(all_overviews) != 1:
        reasons.append(
            f"section contains {len(all_overviews)} overview papers; title-based split requires review"
        )
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} participant papers")
    if overview.get("pdf_url") is None:
        reasons.append("overview has no official PDF link")
    if any(paper.get("pdf_url") is None for paper in participants):
        reasons.append("at least one participant has no official PDF link")
    if unresolved:
        reasons.append(f"{len(unresolved)} participant papers could not be assigned uniquely")
    participant_urls = [paper["pdf_url"] for paper in participants if paper.get("pdf_url")]
    if len(participant_urls) != len(set(participant_urls)):
        reasons.append("duplicate participant PDF URL")
    shared = [paper for paper in participants if paper.get("pdf_url") in duplicated_participant_urls]
    if shared:
        reasons.append(f"{len(shared)} participant paper(s) also occur in another FIRE section")

    task_name = track_name if len(all_overviews) == 1 else clean_task_name(overview["title"], track_name)
    task_slug = slugify(task_name)
    if len(all_overviews) != 1:
        # Several FIRE volumes publish multiple subtrack overviews under one
        # umbrella heading (especially HASOC).  The overview source id is a
        # stable, source-provided discriminator when cleaned titles collide.
        task_slug = f"{task_slug}-{slugify(Path(urlparse(overview['pdf_url']).path).stem)}"
    task_id = f"fire{edition['year']}-{task_slug}"
    confidence = "high" if not reasons else "medium"
    decision = "include" if confidence == "high" else "review"
    overview_key = normalize_title(overview["title"])
    candidate = {
        "task_id": task_id,
        "venue": task_name,
        "parent_venue": "FIRE",
        "year": edition["year"],
        "task_name": task_name,
        "ceur_volume": edition.get("ceur_volume"),
        "source": {
            "provider": "ceur_fire" if edition.get("ceur_volume") else "fire_archive",
            "collection_id": edition["collection_id"],
            "proceedings_url": edition["proceedings_url"],
            "official_url": edition["official_url"],
            "track_name": track_name,
            "dblp_url": edition["dblp_url"],
            "tira_refs": tira_refs,
        },
        "overview": {
            **paper_record(overview, track_name, edition["collection_id"], tira_refs),
            "is_umbrella": False,
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
            "task_assignment_method": "section_grouping" if len(all_overviews) == 1 else "title_heuristic",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
            "dblp_overview_match": bool(dblp_titles and overview_key in dblp_titles),
            "tira_track_matches": tira_refs,
        },
        "screening": {
            "decision": decision,
            "checks": {
                "one_overview": len(all_overviews) == 1,
                "official_track_section": bool(track_name),
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": overview.get("pdf_url") is not None and all(
                    paper.get("pdf_url") is not None for paper in participants
                ),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
                "no_multi_track_participants": not shared,
                "unique_title_assignment": not unresolved,
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers; confidence=%s)",
        task_id,
        decision,
        len(participants),
        confidence,
    )
    return candidate


def collect_edition(edition: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect candidates from one cached FIRE edition."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    proceedings_path = edition_dir / "proceedings.html"
    official_path = edition_dir / "official.html"
    sections: list[dict] = []
    if edition.get("ceur_volume") and proceedings_path.exists():
        sections = parse_ceur_volume(
            proceedings_path.read_text(encoding="utf-8"), edition["ceur_volume"]
        )
    elif official_path.exists():
        sections = parse_legacy_fire_page(
            official_path.read_text(encoding="utf-8"), edition["official_url"]
        )
    if not sections:
        return [], [{
            "record_type": "unresolved_fire_edition",
            "venue": "FIRE",
            "year": edition["year"],
            "collection_id": edition["collection_id"],
            "decision": "review",
            "reason": "no parseable official FIRE proceedings sections with PDF links",
            "source": edition,
        }], []

    dblp_path = RAW_DIR / "dblp" / f"{edition['collection_id']}.html"
    dblp_titles = parse_dblp_titles(dblp_path.read_text(encoding="utf-8")) if dblp_path.exists() else set()
    tira_path = RAW_DIR / "tira-tasks.html"
    tira_html = tira_path.read_text(encoding="utf-8") if tira_path.exists() else ""

    normalized_sections = []
    for section in sections:
        section_name = clean_text(section.get("lab_name", ""))
        if not section_name or EXCLUDED_SECTION_RE.search(section_name):
            continue
        papers = prepare_papers(section)
        if papers:
            normalized_sections.append({"lab_name": section_name, "papers": papers})

    occurrences: defaultdict[str, set[str]] = defaultdict(set)
    for section in normalized_sections:
        for paper in section["papers"]:
            if not paper["is_overview"]:
                occurrences[paper["pdf_url"]].add(section["lab_name"])
    duplicated = {url for url, section_names in occurrences.items() if len(section_names) > 1}

    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    for section in normalized_sections:
        papers = section["papers"]
        overviews = [paper for paper in papers if paper["is_overview"]]
        if not overviews:
            review.append({
                "record_type": "unresolved_fire_section",
                "venue": "FIRE",
                "year": edition["year"],
                "track_name": section["lab_name"],
                "decision": "review",
                "reason": "official section has no recognizable overview paper",
                "papers": papers,
            })
            continue

        if len(overviews) == 1:
            assignments = {id(overviews[0]): [paper for paper in papers if paper is not overviews[0]]}
            unresolved = []
        else:
            assignments, unresolved = assign_by_title(papers, overviews, logger, section["lab_name"])

        for overview in overviews:
            participants = assignments.get(id(overview), [])
            tira_refs = parse_tira_refs(tira_html, edition["year"], section["lab_name"])
            candidate = build_task_candidate(
                section,
                edition,
                overview,
                participants,
                overviews,
                duplicated,
                unresolved,
                dblp_titles,
                tira_refs,
                logger,
            )
            candidates.append(candidate)
            if candidate["provenance"]["confidence"] != "high":
                review.append(candidate)

    logger.info(
        "FIRE %s: parsed %d sections, %d candidates, %d review records",
        edition["year"],
        len(normalized_sections),
        len(candidates),
        len(review),
    )
    return candidates, review, excluded


def write_screening_report(
    candidates: list[dict], review: list[dict], excluded: list[dict], path: Path
) -> None:
    """Write the generated FIRE screening report."""
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# FIRE screening report",
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
        f"- `{candidate['task_id']}` — {len(candidate['participants'])} participants — "
        f"overview: {candidate['overview']['paper_url']}"
        for candidate in high
    )
    lines += ["", "## Review records", ""]
    for record in review:
        if "task_id" in record:
            reasons = "; ".join(record["provenance"].get("confidence_reasons", [])) or "unspecified"
            lines.append(f"- `{record['task_id']}` — {reasons}")
        else:
            lines.append(
                f"- FIRE {record.get('year')} {record.get('track_name', record.get('collection_id', 'edition'))} — "
                f"{record.get('reason', 'review')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger) -> bool:
    """Process all selected cached FIRE editions and write source outputs."""
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured FIRE edition for year %s", year)
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
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, CANDIDATES_DIR / "fire.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "fire.jsonl")
    write_jsonl(review, SCREENING_DIR / "fire_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "fire_excluded.jsonl")
    write_screening_report(candidates, review, excluded, SCREENING_DIR / "fire_report.md")
    logger.info(
        "wrote %d FIRE candidates (%d high, %d review) to %s",
        len(candidates),
        sum(1 for candidate in candidates if candidate["provenance"]["confidence"] == "high"),
        len(review),
        CANDIDATES_DIR / "fire.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and screen FIRE task candidates from cached proceedings.")
    parser.add_argument("--year", type=int, help="Collect only one configured FIRE year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_fire")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
