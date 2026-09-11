#!/usr/bin/env python
"""Collect high-precision SemEval task candidates from ACL Anthology pages.

SemEval proceedings place organizer task papers and participant papers in one volume.
This collector assigns a paper only when the title contains an explicit year and task
number.  Ambiguous records are retained for review and never receive high confidence.
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
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import slugify, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, SCREENING_DIR
from src.semeval_config import selected_volumes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "acl_anthology" / "semeval"
LOGS_DIR = PROJECT_ROOT / "logs"

TASK_RE = re.compile(
    # ACL titles frequently concatenate the team name and venue, e.g.
    # ``TeamNameatSemEval-2025 Task 3``.  Do not require a word boundary before
    # ``SemEval`` or those valid participant titles cannot be assigned.
    r"SemEval[- ](?P<year>20\d{2})\s+Task[- ]?(?P<number>\d{1,2})\b",
    re.IGNORECASE,
)
ORGANIZER_RE = re.compile(r"^\s*SemEval[- ]20\d{2}\s+Task[- ]?\d+\b", re.IGNORECASE)
# Both ``Team at SemEval`` and the common compact ``TeamatSemEval`` form occur.
PARTICIPANT_RE = re.compile(r"(?:\bat\s*|at)SemEval[- ]20\d{2}\s+Task[- ]?\d+\b", re.IGNORECASE)
PAPER_ID_RE = re.compile(r"^/(?P<id>[^/]+\.\d+)/?$")
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_semeval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def clean_html_text(node) -> str:
    """Read an ACL title/author while preserving text split across markup spans."""
    return re.sub(r"\s+", " ", node.get_text("", strip=True)).strip()


def find_paper_container(title_link):
    """Find the smallest ancestor containing the title's PDF link."""
    current = title_link
    while current is not None:
        pdf_link = current.find("a", href=PDF_RE)
        if pdf_link is not None:
            return current, pdf_link
        current = current.parent
    return title_link.parent, None


def parse_papers(raw_html: str, volume: dict) -> list[dict]:
    """Parse task-paper metadata and source-provided PDF links from one volume page."""
    soup = BeautifulSoup(raw_html, "lxml")
    base_url = volume["url"]
    papers: list[dict] = []
    for title_link in soup.select("a.align-middle[href]"):
        match = PAPER_ID_RE.match(title_link.get("href", ""))
        if match is None:
            continue
        paper_id = match.group("id")
        container, pdf_link = find_paper_container(title_link)
        title = clean_html_text(title_link)
        authors = []
        for author_link in container.select('a[href^="/people/"]'):
            author = clean_html_text(author_link)
            if author and author not in authors:
                authors.append(author)
        pdf_url = urljoin(base_url, pdf_link["href"]) if pdf_link is not None else None
        task_match = TASK_RE.search(title)
        papers.append({
            "source_id": paper_id,
            "paper_url": urljoin(base_url, title_link["href"]),
            "pdf_url": pdf_url,
            "title": title,
            "authors": authors,
            "task_year": int(task_match.group("year")) if task_match else None,
            "task_number": int(task_match.group("number")) if task_match else None,
            "is_organizer": bool(ORGANIZER_RE.search(title)),
            "is_participant": bool(PARTICIPANT_RE.search(title)),
        })
    return papers


def task_name_from_title(title: str, task_number: int) -> str:
    """Extract a readable task name from an organizer title."""
    match = TASK_RE.search(title)
    if match is None:
        return f"Task {task_number}"
    name = title[match.end():].lstrip(" :-–—")
    return name or f"Task {task_number}"


def participant_record(paper: dict, volume: dict) -> dict:
    """Convert a parsed ACL paper into the common participant record shape."""
    team_match = PARTICIPANT_RE.search(paper["title"])
    team_name = paper["title"][:team_match.start()].strip() if team_match else None
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": paper["pdf_url"],
        "team_name": team_name or None,
        "code_urls": [],
        "tira_refs": [],
        "source_id": paper["source_id"],
        "paper_url": paper["paper_url"],
        "source_collection_id": volume["collection_id"],
    }


def overview_record(paper: dict, volume: dict) -> dict:
    """Convert a parsed ACL paper into the common overview record shape."""
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": paper["pdf_url"],
        "source_id": paper["source_id"],
        "paper_url": paper["paper_url"],
        "source_collection_id": volume["collection_id"],
        "is_umbrella": False,
    }


def build_task_candidate(group: list[dict], volume: dict, logger: logging.Logger) -> dict | None:
    """Build one task candidate and classify it as high confidence or review."""
    task_number = group[0]["task_number"]
    organizers = [paper for paper in group if paper["is_organizer"]]
    participants = [paper for paper in group if paper["is_participant"] and not paper["is_organizer"]]
    other_task_papers = [
        paper for paper in group
        if not paper["is_organizer"] and not paper["is_participant"]
    ]
    if not organizers:
        logger.warning(
            "%s Task %s: no explicit organizer paper; keeping %d papers in review",
            volume["year"], task_number, len(group),
        )
        return None

    overview = organizers[0]
    task_name = task_name_from_title(overview["title"], task_number)
    task_id = f"semeval{volume['year']}-task-{task_number}-{slugify(task_name)}"
    reasons: list[str] = []
    if len(organizers) != 1:
        reasons.append(f"expected exactly one organizer paper, found {len(organizers)}")
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} explicit participant papers")
    if overview["pdf_url"] is None:
        reasons.append("organizer paper has no source-provided PDF link")
    if any(paper["pdf_url"] is None for paper in participants):
        reasons.append("at least one participant has no source-provided PDF link")
    if other_task_papers:
        reasons.append(
            f"found {len(other_task_papers)} paper(s) with a task number but no canonical participant marker"
        )
    participant_urls = [paper["pdf_url"] for paper in participants if paper["pdf_url"]]
    if len(participant_urls) != len(set(participant_urls)):
        reasons.append("duplicate participant PDF URL")

    confidence = "high" if not reasons else "medium"
    decision = "include" if confidence == "high" else "review"
    candidate = {
        "task_id": task_id,
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": volume["year"],
        "task_number": task_number,
        "task_name": task_name,
        "ceur_volume": None,
        "source": {
            "provider": volume["provider"],
            "collection_id": volume["collection_id"],
            "proceedings_url": volume["url"],
        },
        "overview": overview_record(overview, volume),
        "participants": [participant_record(paper, volume) for paper in participants],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": "explicit_task_number",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
        },
        "screening": {
            "decision": decision,
            "checks": {
                "one_overview": len(organizers) == 1,
                "explicit_task_numbers": not other_task_papers,
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": overview["pdf_url"] is not None and all(
                    paper["pdf_url"] is not None for paper in participants
                ),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers; confidence=%s)",
        task_id, decision, len(participants), confidence,
    )
    return candidate


def collect_volume(volume: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict], int]:
    """Collect candidate, review, and excluded records from one cached volume."""
    raw_path = RAW_DIR / f"{volume['collection_id']}.html"
    if not raw_path.exists():
        raise FileNotFoundError(f"missing cached ACL Anthology page: {raw_path}")
    papers = parse_papers(raw_path.read_text(encoding="utf-8"), volume)
    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    unassigned = 0
    for paper in papers:
        if paper["task_year"] != volume["year"] or paper["task_number"] is None:
            unassigned += 1
            review.append({
                "record_type": "unassigned_semeval_paper",
                "venue": "SemEval",
                "year": volume["year"],
                "decision": "review",
                "reason": "paper title has no explicit SemEval task number",
                "paper": paper,
            })
            continue
        grouped[(paper["task_year"], paper["task_number"])].append(paper)

    for group in grouped.values():
        candidate = build_task_candidate(group, volume, logger)
        if candidate is None:
            review.append({
                "record_type": "unresolved_semeval_task",
                "venue": "SemEval",
                "year": volume["year"],
                "task_number": group[0]["task_number"],
                "decision": "review",
                "reason": "no explicit organizer paper",
                "papers": group,
            })
            continue
        candidates.append(candidate)
        if candidate["provenance"]["confidence"] != "high":
            review.append(candidate)

    logger.info(
        "%s: parsed %d papers, %d task groups, %d unassigned/non-task papers",
        volume["collection_id"], len(papers), len(grouped), unassigned,
    )
    return candidates, review, excluded, unassigned


def write_screening_report(
    candidates: list[dict], review: list[dict], excluded: list[dict], unassigned: int, path: Path,
) -> None:
    """Write a compact human-readable report without replacing the machine records."""
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# SemEval screening report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate tasks: {len(candidates)}",
        f"High-confidence tasks: {len(high)}",
        f"Tasks needing review: {len(review)}",
        f"Excluded records: {len(excluded)}",
        f"Unassigned/non-task papers: {unassigned}",
        "",
        "## High-confidence tasks",
        "",
    ]
    for candidate in high:
        lines.append(
            f"- `{candidate['task_id']}` — {len(candidate['participants'])} participants — "
            f"overview: {candidate['overview']['paper_url']}"
        )
    lines += ["", "## Tasks needing review", ""]
    for candidate in review:
        if "task_id" in candidate:
            reasons = "; ".join(candidate["provenance"].get("confidence_reasons", [])) or "unspecified"
            lines.append(f"- `{candidate['task_id']}` — {reasons}")
        elif candidate.get("record_type") == "unassigned_semeval_paper":
            paper = candidate.get("paper", {})
            lines.append(f"- paper `{paper.get('source_id', 'unknown')}` — {candidate['reason']}")
        else:
            lines.append(
                f"- SemEval {candidate['year']} Task {candidate.get('task_number')} — {candidate['reason']}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger) -> bool:
    """Process all selected cached SemEval volumes and write source screening files."""
    volumes = selected_volumes(year)
    if not volumes:
        logger.error("no configured SemEval volume for year %s", year)
        return False

    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    unassigned = 0
    try:
        for volume in volumes:
            volume_candidates, volume_review, volume_excluded, volume_unassigned = collect_volume(volume, logger)
            candidates.extend(volume_candidates)
            review.extend(volume_review)
            excluded.extend(volume_excluded)
            unassigned += volume_unassigned
    except (FileNotFoundError, ValueError) as exc:
        logger.error("SemEval collection failed: %s", exc)
        return False

    candidates.sort(key=lambda candidate: candidate["task_id"])
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, CANDIDATES_DIR / "semeval.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "semeval.jsonl")
    write_jsonl(review, SCREENING_DIR / "semeval_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "semeval_excluded.jsonl")
    write_screening_report(
        candidates, review, excluded, unassigned,
        SCREENING_DIR / "semeval_report.md",
    )
    logger.info(
        "wrote %d SemEval candidates (%d high, %d review) to %s",
        len(candidates),
        sum(1 for candidate in candidates if candidate["provenance"]["confidence"] == "high"),
        len(review),
        CANDIDATES_DIR / "semeval.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and screen SemEval task candidates from cached ACL Anthology pages.")
    parser.add_argument("--year", type=int, help="Collect only one configured SemEval year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_semeval")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
