#!/usr/bin/env python
"""Merge source-specific task candidates into the existing canonical files."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import candidate_issues, candidate_sort_key, demote, read_jsonl, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, INTERMEDIATE_DIR, SCREENING_DIR


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"merge_candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def load_source_candidates(logger: logging.Logger) -> list[dict]:
    """Load all source files, with a compatibility fallback for old CLEF runs."""
    source_files = sorted(CANDIDATES_DIR.glob("*.jsonl"))
    if not source_files:
        legacy = INTERMEDIATE_DIR / "all_candidates.jsonl"
        source_files = [legacy] if legacy.exists() else []
    records: list[dict] = []
    for path in source_files:
        source_records = read_jsonl(path)
        logger.info("loaded %d candidates from %s", len(source_records), path)
        records.extend(source_records)
    return records


def demote_duplicates(candidates: list[dict], logger: logging.Logger) -> None:
    """Demote every candidate involved in a cross-task ID or PDF collision."""
    by_task_id: dict[str, list[dict]] = defaultdict(list)
    by_pdf_url: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        by_task_id[candidate.get("task_id", "")].append(candidate)
        overview = candidate.get("overview") or {}
        if overview.get("pdf_url"):
            by_pdf_url[overview["pdf_url"]].append(candidate)
        for participant in candidate.get("participants", []):
            if participant.get("pdf_url"):
                by_pdf_url[participant["pdf_url"]].append(candidate)

    for task_id, matches in by_task_id.items():
        if task_id and len(matches) > 1:
            reason = f"duplicate task_id across sources: {task_id}"
            logger.warning(reason)
            for candidate in matches:
                demote(candidate, [reason])
    for pdf_url, matches in by_pdf_url.items():
        task_ids = {candidate.get("task_id") for candidate in matches}
        if pdf_url and len(task_ids) > 1:
            reason = f"PDF URL appears in multiple tasks: {pdf_url}"
            logger.warning(reason)
            for candidate in matches:
                demote(candidate, [reason])


def merge(logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Merge candidates and return (all candidates, review records, rejected records)."""
    candidates = load_source_candidates(logger)
    valid_candidates: list[dict] = []
    review: list[dict] = []
    rejected: list[dict] = []
    for path in sorted(SCREENING_DIR.glob("*_excluded.jsonl")):
        rejected.extend(read_jsonl(path))
    for candidate in candidates:
        issues = candidate_issues(candidate)
        if issues:
            demote(candidate, issues)
            logger.warning("%s moved to review: %s", candidate.get("task_id", "unknown"), "; ".join(issues))
        valid_candidates.append(candidate)

    demote_duplicates(valid_candidates, logger)
    valid_candidates.sort(key=candidate_sort_key)
    review.extend(candidate for candidate in valid_candidates if candidate.get("provenance", {}).get("confidence") != "high")
    # Source review files may repeat medium-confidence candidates already present in
    # the source candidate file. Only append unresolved records that cannot enter the
    # common candidate list because they have no overview paper yet.
    for path in sorted(SCREENING_DIR.glob("*_review.jsonl")):
        review.extend(record for record in read_jsonl(path) if "task_id" not in record)
    return valid_candidates, review, rejected


def write_report(candidates: list[dict], review: list[dict], rejected: list[dict], path: Path) -> None:
    """Write source totals plus auditable decisions and links for every record."""
    by_source: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        by_source[(candidate.get("source") or {}).get("provider", "legacy")] += 1
    lines = [
        "# Candidate merge report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Merged candidates: {len(candidates)}",
        f"High-confidence candidates: {sum(1 for c in candidates if c.get('provenance', {}).get('confidence') == 'high')}",
        f"Candidates needing review: {len(review)}",
        f"Excluded records: {len(rejected)}",
        "",
        "## Candidates by source",
        "",
    ]
    for source, count in sorted(by_source.items()):
        lines.append(f"- {source}: {count}")
    lines += [
        "",
        "## Candidate decisions",
        "",
        "| Task | Source | Decision | Confidence | Participants | Overview | Proceedings | Reasons |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for candidate in candidates:
        source = candidate.get("source") or {}
        provenance = candidate.get("provenance") or {}
        confidence = provenance.get("confidence", "unknown")
        decision = (candidate.get("screening") or {}).get(
            "decision", "include" if confidence == "high" else "review"
        )
        overview = candidate.get("overview") or {}
        reasons = "; ".join(provenance.get("confidence_reasons", [])) or "—"
        lines.append(
            f"| `{candidate.get('task_id', 'unknown')}` | {source.get('provider', 'legacy')} | "
            f"{decision} | {confidence} | {len(candidate.get('participants', []))} | "
            f"[{overview.get('source_id', 'paper')}]({overview.get('paper_url') or overview.get('pdf_url', '')}) | "
            f"[{source.get('collection_id', 'source')}]({source.get('proceedings_url', '')}) | {reasons} |"
        )
    unresolved = [record for record in review if "task_id" not in record]
    lines += ["", "## Unresolved review records", ""]
    if not unresolved:
        lines.append("None.")
    for record in unresolved:
        paper = record.get("paper") or {}
        link = paper.get("paper_url") or paper.get("pdf_url")
        label = paper.get("source_id", record.get("record_type", "record"))
        if link:
            label = f"[{label}]({link})"
        lines.append(
            f"- {record.get('record_type', 'review record')} — {label} — {record.get('reason', 'review')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge CLEF and source-specific shared-task candidates.")
    parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("merge_candidates")
    logger.info("logging to %s", log_path)
    candidates, review, rejected = merge(logger)
    if not candidates:
        logger.error("no candidate records found — run group_tasks.py and source collectors first")
        raise SystemExit(1)
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, INTERMEDIATE_DIR / "all_candidates.jsonl")
    write_jsonl(review, INTERMEDIATE_DIR / "needs_review.jsonl")
    write_jsonl(rejected, INTERMEDIATE_DIR / "rejected_candidates.jsonl")
    write_report(candidates, review, rejected, SCREENING_DIR / "merged_report.md")
    logger.info(
        "wrote %d candidates and %d review records; high-confidence=%d",
        len(candidates), len(review),
        sum(1 for c in candidates if c.get("provenance", {}).get("confidence") == "high"),
    )


if __name__ == "__main__":
    main()
