#!/usr/bin/env python
"""Collect SISAP Indexing Challenge task candidates from official sources.

SISAP publishes one annual challenge with several sub-tasks and a single organizer
overview covering all of them.  Each edition therefore becomes one umbrella task
whose participants carry the sub-task numbers they addressed, so no document is
stored in more than one task.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import slugify, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, SCREENING_DIR
from src.sisap_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "sisap"
LOGS_DIR = PROJECT_ROOT / "logs"

PDF_TEMPLATE = "https://link.springer.com/content/pdf/{doi}.pdf"
SPRINGER_DOI_RE = re.compile(r"10\.1007/[0-9A-Za-z.\-]+_[0-9]+")
TASK_RE = re.compile(r"\btask\s*([A-C]|[1-9][0-9]*)\b", re.IGNORECASE)


def setup_logging() -> Path:
    """Create a readable write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_sisap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    """Collapse HTML whitespace while retaining meaningful punctuation."""
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def parse_task_page(raw_html: str, configured_tasks: list[dict]) -> dict[str, dict]:
    """Extract task headings and descriptions from an official SISAP task page."""
    soup = BeautifulSoup(raw_html, "lxml")
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    parsed: dict[str, dict] = {}
    for task in configured_tasks:
        number = str(task["number"])
        target = task["short_name"].casefold()
        heading = None
        for candidate in headings:
            label = clean_text(candidate.get_text(" ", strip=True))
            if target in label.casefold():
                heading = candidate
                break
            match = TASK_RE.search(label)
            if match and match.group(1).casefold() == number.casefold():
                heading = candidate
                break
        description_parts: list[str] = []
        if heading is not None:
            level = int(heading.name[1])
            sibling = heading.find_next_sibling()
            while sibling is not None:
                if getattr(sibling, "name", "").startswith("h"):
                    sibling_level = int(sibling.name[1])
                    if sibling_level <= level:
                        break
                text = clean_text(sibling.get_text(" ", strip=True)) if hasattr(sibling, "get_text") else ""
                if text:
                    description_parts.append(text)
                sibling = sibling.find_next_sibling()
        parsed[number] = {
            **task,
            "official_heading": clean_text(heading.get_text(" ", strip=True)) if heading else None,
            "description": " ".join(description_parts),
            "found": heading is not None,
        }
    return parsed


def _doi_from_href(href: str) -> str | None:
    match = SPRINGER_DOI_RE.search(href)
    return match.group(0) if match else None


def parse_springer_indexing_challenge(raw_html: str, base_url: str) -> list[dict]:
    """Parse the Indexing Challenge section of a Springer proceedings ToC."""
    soup = BeautifulSoup(raw_html, "lxml")
    section_heading = next(
        (
            heading for heading in soup.find_all(re.compile(r"^h[1-6]$"))
            # 2025 titles the part "SISAP Indexing Challenge"; other years omit "SISAP".
            if clean_text(heading.get_text(" ", strip=True)).casefold() in {"indexing challenge", "sisap indexing challenge"}
        ),
        None,
    )
    if section_heading is None:
        return []
    chapter_list = section_heading.find_next("ol")
    if chapter_list is None:
        return []
    papers: list[dict] = []
    for position, item in enumerate(chapter_list.find_all("li", attrs={"data-test": "chapter"}, recursive=False), start=1):
        title_node = item.find(re.compile(r"^h[1-6]$"), attrs={"data-test": re.compile(r"chapter-title")})
        if title_node is None:
            title_node = item.find(re.compile(r"^h[1-6]$"))
        if title_node is None or clean_text(title_node.get_text(" ", strip=True)).casefold() == "front matter":
            continue
        anchor = title_node.find("a", href=True)
        if anchor is None:
            continue
        paper_url = urljoin(base_url, anchor["href"])
        doi = _doi_from_href(paper_url)
        if doi is None:
            continue
        authors_node = item.find(class_=re.compile(r"app-author-list"))
        authors_text = clean_text(authors_node.get_text(" ", strip=True)) if authors_node else ""
        authors = [authors_text] if authors_text else []
        page_node = item.find(attrs={"data-test": "page-number"})
        papers.append({
            "title": clean_text(anchor.get_text(" ", strip=True)),
            "authors": authors,
            "paper_url": paper_url,
            "pdf_url": PDF_TEMPLATE.format(doi=doi),
            "doi": doi,
            "source_id": doi.replace("/", "_"),
            "position": position,
            "pages": clean_text(page_node.get_text(" ", strip=True)) if page_node else None,
            "role": "overview" if "overview of" in clean_text(anchor.get_text(" ", strip=True)).casefold() else "participant",
        })
    return papers


def parse_2025_results(raw_html: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """Parse the official 2025 team table and per-task result tables."""
    soup = BeautifulSoup(raw_html, "lxml")
    participants: list[dict] = []
    result_tables: dict[str, list[dict]] = {}
    for table_index, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        lowered = [header.casefold() for header in headers]
        parsed_rows = []
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
            if not values:
                continue
            record = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
            parsed_rows.append(record)
        if "team" in lowered and "task" in lowered:
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
                if len(values) < 3:
                    continue
                team = values[0]
                task_cell = values[2]
                task_numbers = [int(value) for value in re.findall(r"\b[12]\b", task_cell)]
                paper_anchor = cells[3].find("a", href=True) if len(cells) > 3 else None
                repo_anchor = cells[4].find("a", href=True) if len(cells) > 4 else None
                paper_url = urljoin("https://sisap-challenges.github.io/2025/evaluation/", paper_anchor["href"]) if paper_anchor else None
                doi = _doi_from_href(paper_url or "")
                participants.append({
                    "team_name": team,
                    "members": values[1] if len(values) > 1 else "",
                    "task_numbers": task_numbers,
                    "paper_title": clean_text(paper_anchor.get_text(" ", strip=True)) if paper_anchor else None,
                    "paper_url": paper_url,
                    "pdf_url": PDF_TEMPLATE.format(doi=doi) if doi else None,
                    "doi": doi,
                    "code_urls": [repo_anchor["href"]] if repo_anchor else [],
                    "source_id": doi.replace("/", "_") if doi else slugify(team),
                })
        elif "team" in lowered:
            task_match = next((re.search(r"task\s*([12])", heading, re.IGNORECASE) for heading in headers), None)
            task_number = task_match.group(1) if task_match else str(table_index)
            result_tables[task_number] = parsed_rows
    return participants, result_tables


def parse_csv_records(path: Path) -> list[dict]:
    """Read a cached challenge CSV without adding pandas as a dependency."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def result_records_for_edition(edition: dict, edition_dir: Path, task_number: str) -> list[dict]:
    """Return quantitative rows associated with one task unit."""
    year = edition["year"]
    if year == 2023:
        rows = parse_csv_records(edition_dir / "github_result_csv.csv")
        if task_number == "A":
            return [row for row in rows if row.get("data", "").casefold().startswith("clip")]
        return [row for row in rows if row.get("data", "").casefold().startswith("hamming")]
    if year == 2024:
        return parse_csv_records(edition_dir / f"github_task{task_number}_results.csv")
    if year == 2025:
        evaluation_path = edition_dir / "evaluation.html"
        if not evaluation_path.exists():
            return []
        _, tables = parse_2025_results(evaluation_path.read_text(encoding="utf-8"))
        return tables.get(task_number, [])
    if year == 2026:
        return [row for path in sorted(edition_dir.glob(f"github_task{task_number}_*test.csv")) for row in parse_csv_records(path)]
    return []


def _paper_record(paper: dict, edition: dict, task_name: str) -> dict:
    return {
        "title": paper["title"],
        "authors": paper.get("authors", []),
        "pdf_url": paper["pdf_url"],
        "team_name": paper.get("team_name"),
        "code_urls": [],
        "tira_refs": [edition["tira_url"]] if edition.get("tira_url") else [],
        "source_id": paper["source_id"],
        "paper_url": paper["paper_url"],
        "source_format": "pdf",
        "track_name": task_name,
        "source_collection_id": edition["collection_id"],
        "paper_type": "organizer_overview" if paper.get("role") == "overview" else "participant_notebook",
    }


def build_edition_candidate(
    edition: dict,
    subtasks: list[dict],
    overview: dict | None,
    participants: list[dict],
    unpublished_configured: list[str],
    logger: logging.Logger,
) -> dict:
    """Build the one umbrella task of an edition: its overview covers every sub-task."""
    task_id = f"sisap{edition['year']}-indexing-challenge"
    task_name = f"SISAP {edition['year']} Indexing Challenge"
    reasons: list[str] = []
    if overview is None:
        reasons.append("no published organizer overview found in the proceedings")
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} published participant paper(s)")
    missing_headings = [str(subtask["number"]) for subtask in subtasks if not subtask["task_metadata"].get("found")]
    if missing_headings:
        reasons.append(f"official task heading not found for sub-task(s) {', '.join(missing_headings)}")
    unmapped = [paper["doi"] for paper in participants if not paper.get("team_name") or not paper.get("task_numbers")]
    if unmapped:
        reasons.append(f"participant paper(s) without a configured team/sub-task mapping: {', '.join(unmapped)}")
    if unpublished_configured:
        reasons.append(f"configured paper(s) missing from the proceedings: {', '.join(unpublished_configured)}")
    confidence = "medium" if reasons else "high"
    participant_urls = [paper["pdf_url"] for paper in participants]
    candidate = {
        "task_id": task_id,
        "venue": task_name,
        "parent_venue": "SISAP",
        "year": edition["year"],
        "task_name": task_name,
        "ceur_volume": None,
        "source": {
            "provider": "sisap_indexing_challenge",
            "collection_id": edition["collection_id"],
            "official_url": edition["official_url"],
            "tasks_url": edition.get("tasks_url"),
            "methodology_url": edition.get("methodology_url"),
            "evaluation_url": edition.get("evaluation_url"),
            "proceedings_url": edition.get("proceedings_url"),
            "conference_url": edition.get("conference_url"),
            "dblp_url": edition.get("dblp_url"),
            "tira_refs": [edition["tira_url"]] if edition.get("tira_url") else [],
            "subtasks": subtasks,
        },
        "overview": {
            **_paper_record(overview or {
                "title": f"SISAP {edition['year']} Indexing Challenge overview unavailable",
                "pdf_url": "",
                "source_id": "overview-unavailable",
                "paper_url": edition.get("overview_url", ""),
                "role": "overview",
            }, edition, task_name),
            "is_umbrella": len(subtasks) > 1,
        },
        "participants": [
            {**_paper_record(paper, edition, task_name), "task_numbers": paper["task_numbers"]}
            for paper in participants
        ],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": "edition_umbrella_overview_with_configured_subtasks",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
            "official_task_evidence": not missing_headings,
            "official_proceedings_evidence": bool(overview or participants),
            "result_evidence_rows": sum(len(subtask["result_records"]) for subtask in subtasks),
        },
        "screening": {
            "decision": "include" if confidence == "high" else "review",
            "checks": {
                "one_overview": overview is not None,
                "official_task_section": not missing_headings,
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": bool(overview and overview.get("pdf_url")) and all(participant_urls),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
                "explicit_task_mapping": not unmapped,
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers over %d sub-tasks; confidence=%s)",
        task_id, candidate["screening"]["decision"], len(participants), len(subtasks), confidence,
    )
    return candidate


def collect_edition(edition: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect one SISAP edition as a single umbrella task from cached sources."""
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    tasks_path = edition_dir / "tasks.html"
    if not tasks_path.exists():
        # 2025/2026 use the edition landing page as their task page; the fetcher
        # de-duplicates identical URLs and stores that page as ``official.html``.
        tasks_path = edition_dir / "official.html"
    task_page_data = parse_task_page(
        tasks_path.read_text(encoding="utf-8") if tasks_path.exists() else "",
        edition["tasks"],
    )
    proceedings: list[dict] = []
    for filename in ("proceedings.html", "proceedings_2.html"):
        proceedings_path = edition_dir / filename
        if proceedings_path.exists():
            known = {paper["doi"] for paper in proceedings}
            proceedings.extend(
                paper for paper in parse_springer_indexing_challenge(
                    proceedings_path.read_text(encoding="utf-8"),
                    edition.get("proceedings_url", "https://link.springer.com/"),
                )
                if paper["doi"] not in known
            )
    overview = next((paper for paper in proceedings if paper["role"] == "overview"), None)
    configured = edition.get("papers", {})
    participants = []
    for paper in proceedings:
        if paper["role"] != "participant":
            continue
        mapping = configured.get(paper["doi"], {})
        participants.append({**paper, "team_name": mapping.get("team"), "task_numbers": mapping.get("tasks", [])})
    published = {paper["doi"] for paper in participants}
    subtasks = [
        {
            "number": task["number"],
            "name": task["name"],
            "task_metadata": task_page_data.get(str(task["number"]), task),
            "result_records": result_records_for_edition(edition, edition_dir, str(task["number"])),
        }
        for task in edition["tasks"]
    ]
    candidate = build_edition_candidate(
        edition, subtasks, overview, participants, sorted(set(configured) - published), logger
    )
    review = [candidate] if candidate["provenance"]["confidence"] != "high" else []
    return [candidate], review, []


def write_screening_report(candidates: list[dict], review: list[dict], excluded: list[dict], path: Path) -> None:
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# SISAP screening report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate task records: {len(candidates)}",
        f"High-confidence tasks: {len(high)}",
        f"Tasks/records needing review: {len(review)}",
        f"Excluded records: {len(excluded)}",
        "",
        "## High-confidence tasks",
        "",
    ]
    lines.extend(
        f"- `{candidate['task_id']}` — {len(candidate['participants'])} participant papers — "
        f"overview: {candidate['overview'].get('paper_url') or candidate['overview'].get('pdf_url', '')}"
        for candidate in high
    )
    lines.extend(["", "## Review records", ""])
    for record in review:
        if "task_id" in record:
            reasons = "; ".join(record.get("provenance", {}).get("confidence_reasons", [])) or "review"
            lines.append(f"- `{record['task_id']}` — {reasons}")
        else:
            lines.append(
                f"- SISAP {record.get('year')} {record.get('task_name', record.get('collection_id', 'unknown'))} — "
                f"{record.get('reason', 'review')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(year: int | None, logger: logging.Logger) -> bool:
    editions = selected_editions(year)
    if not editions:
        logger.error("no configured SISAP edition for year %s", year)
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
    review.sort(key=lambda record: record.get("task_id", f"{record.get('year', 0)}-{record.get('task_number', '')}"))
    write_jsonl(candidates, CANDIDATES_DIR / "sisap.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "sisap.jsonl")
    write_jsonl(review, SCREENING_DIR / "sisap_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "sisap_excluded.jsonl")
    write_screening_report(candidates, review, excluded, SCREENING_DIR / "sisap_report.md")
    logger.info(
        "wrote %d SISAP candidates (%d high, %d review) to %s",
        len(candidates),
        sum(1 for candidate in candidates if candidate["provenance"]["confidence"] == "high"),
        len(review),
        CANDIDATES_DIR / "sisap.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect SISAP task candidates from cached official sources.")
    parser.add_argument("--year", type=int, help="Collect only one configured SISAP year.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_sisap")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.year, logger) else 1)


if __name__ == "__main__":
    main()
