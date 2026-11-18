#!/usr/bin/env python
"""Collect curated non-SemEval shared tasks from cached ACL Anthology volume pages.

Each task in ``acl_config.ACL_TASKS`` names its organizer overview and a rule that
selects the participant papers.  Nothing is inferred beyond that rule; a task whose
checks fail is kept as medium confidence for review.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.acl_config import selected_tasks, volume_url
from src.candidate_schema import slugify, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, SCREENING_DIR


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "acl_anthology" / "volumes"
LOGS_DIR = PROJECT_ROOT / "logs"

PAPER_ID_RE = re.compile(r"^/(?P<id>(?:20\d{2}\.[^/]+\.\d+|[A-Z]\d{2}-\d+))/?$")
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
# Front matter is ``2020.x.0`` or an ID ending in ``00`` titled like the proceedings
# (``W14-1700``); a bare ``..00`` ID can also be a real paper in large volumes.
FRONT_MATTER_TITLE_RE = re.compile(r"^(?:Proceedings|Joint Conference)\b", re.IGNORECASE)


def is_front_matter(paper_id: str, title: str) -> bool:
    """Return whether an Anthology entry is the volume's front matter, not a paper."""
    return paper_id.endswith(".0") or (
        paper_id.endswith("00") and bool(FRONT_MATTER_TITLE_RE.search(title))
    )


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_acl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def clean_text(node) -> str:
    """Read an ACL title/author, keeping the page's own spacing between markup spans."""
    return re.sub(r"\s+", " ", node.get_text()).strip()


def parse_volume(raw_html: str, collection_id: str) -> list[dict]:
    """Parse every paper of one volume page in page order, without front matter."""
    soup = BeautifulSoup(raw_html, "lxml")
    base_url = volume_url(collection_id)
    papers: list[dict] = []
    seen: set[str] = set()
    for title_link in soup.select("a.align-middle[href]"):
        match = PAPER_ID_RE.match(title_link.get("href", ""))
        if match is None or match.group("id") in seen:
            continue
        paper_id = match.group("id")
        title = clean_text(title_link)
        if is_front_matter(paper_id, title):
            continue
        seen.add(paper_id)
        container, pdf_link = title_link, None
        while container is not None and pdf_link is None:
            pdf_link = container.find("a", href=PDF_RE)
            if pdf_link is None:
                container = container.parent
        authors: list[str] = []
        for author_link in (container or title_link.parent).select('a[href^="/people/"]'):
            author = clean_text(author_link)
            if author and author not in authors:
                authors.append(author)
        papers.append({
            "source_id": paper_id,
            "paper_url": urljoin(base_url, title_link["href"]),
            "pdf_url": urljoin(base_url, pdf_link["href"]) if pdf_link is not None else None,
            "title": title,
            "authors": authors,
        })
    return papers


def select_participants(task: dict, papers: list[dict], overview_ids: set[str]) -> list[dict]:
    """Apply the task's range, title marker and exclusions to the volume's papers."""
    ids = [paper["source_id"] for paper in papers]
    for key in ("first", "last"):
        if task[key] is not None and task[key] not in ids:
            raise ValueError(f"{task['collection_id']}: configured {key} paper {task[key]} not on the page")
    start = ids.index(task["first"]) if task["first"] else 0
    stop = ids.index(task["last"]) + 1 if task["last"] else len(papers)
    marker = re.compile(task["match"], re.IGNORECASE) if task["match"] else None
    return [
        paper for paper in papers[start:stop]
        if paper["source_id"] not in overview_ids
        and paper["source_id"] not in task["exclude"]
        and (marker is None or marker.search(paper["title"]))
    ]


def assignment_method(task: dict) -> str:
    """Name the evidence used to assign participants to the task."""
    if task["match"]:
        return "title_marker"
    return "curated_range" if task["first"] or task["last"] else "dedicated_volume"


def task_id_for(task: dict) -> str:
    """Return the stable task id, e.g. ``conll2014-grammatical-error-correction``."""
    return f"{slugify(task['parent_venue'])}{task['year']}-{slugify(task['task_name'])}"


def paper_record(paper: dict, collection_id: str, **extra) -> dict:
    """Convert a parsed paper into the common overview/participant record shape."""
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": paper["pdf_url"],
        "source_id": paper["source_id"],
        "paper_url": paper["paper_url"],
        "source_collection_id": collection_id,
        **extra,
    }


def build_candidate(task: dict, papers: list[dict], overview_ids: set[str], logger: logging.Logger) -> dict | None:
    """Build one candidate, or ``None`` when the configured overview is not on the page."""
    by_id = {paper["source_id"]: paper for paper in papers}
    overview = by_id.get(task["overview_id"])
    task_id = task_id_for(task)
    if overview is None:
        logger.error("%s: overview %s not found in %s", task_id, task["overview_id"], task["collection_id"])
        return None
    participants = select_participants(task, papers, overview_ids)

    reasons: list[str] = []
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} participant papers")
    if overview["pdf_url"] is None:
        reasons.append("organizer paper has no source-provided PDF link")
    if any(paper["pdf_url"] is None for paper in participants):
        reasons.append("at least one participant has no source-provided PDF link")
    pdf_urls = [paper["pdf_url"] for paper in participants if paper["pdf_url"]]
    if len(pdf_urls) != len(set(pdf_urls)):
        reasons.append("duplicate participant PDF URL")
    confidence = "high" if not reasons else "medium"

    candidate = {
        "task_id": task_id,
        "venue": task["venue"],
        "parent_venue": task["parent_venue"],
        "year": task["year"],
        "task_name": task["task_name"],
        "ceur_volume": None,
        "source": {
            "provider": task["provider"],
            "collection_id": task["collection_id"],
            "proceedings_url": volume_url(task["collection_id"]),
        },
        "overview": paper_record(overview, task["collection_id"], is_umbrella=False),
        "participants": [
            paper_record(paper, task["collection_id"], team_name=None, code_urls=[], tira_refs=[])
            for paper in participants
        ],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": assignment_method(task),
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
        },
        "screening": {
            "decision": "include" if confidence == "high" else "review",
            "checks": {
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": overview["pdf_url"] is not None and all(p["pdf_url"] for p in participants),
                "unique_pdf_urls": len(pdf_urls) == len(set(pdf_urls)),
            },
        },
    }
    logger.info("%s: %d participant papers; confidence=%s", task_id, len(participants), confidence)
    return candidate


def write_screening_report(candidates: list[dict], review: list[dict], path: Path) -> None:
    """Write a compact human-readable report without replacing the machine records."""
    high = [c for c in candidates if c["provenance"]["confidence"] == "high"]
    lines = [
        "# ACL Anthology screening report", "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate tasks: {len(candidates)}",
        f"High-confidence tasks: {len(high)}",
        f"Tasks needing review: {len(review)}", "",
        "## High-confidence tasks", "",
    ]
    lines += [
        f"- `{c['task_id']}` — {len(c['participants'])} participants "
        f"({c['provenance']['task_assignment_method']}) — overview: {c['overview']['paper_url']}"
        for c in high
    ]
    lines += ["", "## Tasks needing review", ""]
    lines += [
        f"- `{c.get('task_id', c.get('overview_id'))}` — "
        f"{'; '.join(c.get('provenance', {}).get('confidence_reasons', [])) or c.get('reason', 'unspecified')}"
        for c in review
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger, raw_dir: Path = RAW_DIR) -> bool:
    """Process all selected tasks from cached volumes and write source screening files."""
    tasks = selected_tasks(year)
    if not tasks:
        logger.error("no configured ACL Anthology task for year %s", year)
        return False
    overview_ids = {task["overview_id"] for task in tasks}
    pages: dict[str, list[dict]] = {}
    candidates: list[dict] = []
    review: list[dict] = []
    for task in tasks:
        collection_id = task["collection_id"]
        if collection_id not in pages:
            raw_path = raw_dir / f"{collection_id}.html"
            if not raw_path.exists():
                logger.error("missing cached ACL Anthology page: %s", raw_path)
                return False
            pages[collection_id] = parse_volume(raw_path.read_text(encoding="utf-8"), collection_id)
        try:
            candidate = build_candidate(task, pages[collection_id], overview_ids, logger)
        except ValueError as exc:
            logger.error("ACL collection failed: %s", exc)
            return False
        if candidate is None:
            review.append({"record_type": "missing_overview", "overview_id": task["overview_id"],
                           "decision": "review", "reason": "overview paper not found on the volume page"})
            continue
        candidates.append(candidate)
        if candidate["provenance"]["confidence"] != "high":
            review.append(candidate)

    candidates.sort(key=lambda candidate: candidate["task_id"])
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, CANDIDATES_DIR / "acl.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "acl.jsonl")
    write_jsonl(review, SCREENING_DIR / "acl_review.jsonl")
    write_screening_report(candidates, review, SCREENING_DIR / "acl_report.md")
    logger.info("wrote %d ACL candidates (%d review) to %s", len(candidates), len(review), CANDIDATES_DIR / "acl.jsonl")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect curated ACL Anthology shared-task candidates from cached pages.")
    parser.add_argument("--year", type=int, help="Collect only one configured year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_acl")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
