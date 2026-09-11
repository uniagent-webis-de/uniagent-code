"""Shared helpers for source-specific shared-task candidate records.

Collectors for CLEF, SemEval, and future venues write the same small candidate
contract.  The merger keeps this contract stable for the existing document pipeline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def slugify(text: str) -> str:
    """Return a deterministic filesystem/task-id-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def read_jsonl(path: Path) -> list[dict]:
    """Read non-empty JSON Lines records from ``path``."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(records: list[dict], path: Path) -> None:
    """Write JSON Lines records, replacing the previous generated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def candidate_issues(candidate: dict) -> list[str]:
    """Return structural problems that prevent a candidate from being high confidence."""
    issues: list[str] = []
    for field in ("task_id", "venue", "parent_venue", "year", "task_name", "overview", "participants", "provenance"):
        if field not in candidate:
            issues.append(f"missing field: {field}")

    overview = candidate.get("overview")
    if not isinstance(overview, dict):
        issues.append("overview is not an object")
    elif not overview.get("pdf_url"):
        issues.append("overview has no PDF URL")

    participants = candidate.get("participants")
    if not isinstance(participants, list) or not participants:
        issues.append("no participant papers")
    elif any(not isinstance(p, dict) or not p.get("pdf_url") for p in participants):
        issues.append("participant without a PDF URL")

    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("confidence") not in {"high", "medium", "low"}:
        issues.append("invalid provenance confidence")
    return issues


def demote(candidate: dict, reasons: list[str]) -> None:
    """Downgrade a candidate in-place and preserve the automatic reasons."""
    provenance = candidate.setdefault("provenance", {})
    if provenance.get("confidence") == "high":
        provenance["confidence"] = "medium"
    existing = provenance.setdefault("confidence_reasons", [])
    for reason in reasons:
        if reason not in existing:
            existing.append(reason)


def candidate_sort_key(candidate: dict) -> tuple:
    """Sort candidates deterministically by source, year, and task id."""
    source = candidate.get("source") or {}
    return (
        str(candidate.get("parent_venue", "")),
        int(candidate.get("year", 0) or 0),
        str(source.get("collection_id", "")),
        str(candidate.get("task_id", "")),
    )
