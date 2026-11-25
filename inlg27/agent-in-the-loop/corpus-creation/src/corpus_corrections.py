"""Apply reviewed, source-backed corrections without changing unrelated records."""
from __future__ import annotations

import copy
import json
from pathlib import Path

CURATION_DIR = Path(__file__).resolve().parent.parent / "curation"


def apply_metadata_corrections(task: dict, corrections: dict | None = None) -> None:
    """Join curated document fields and existing-task track annotations by stable IDs."""
    if corrections is None:
        corrections = json.loads((CURATION_DIR / "metadata_corrections.json").read_text())
    for document in [task["overview"], *task["participants"]]:
        key = f"{task['task_id']}|{document['pdf_url']}"
        document.update(copy.deepcopy(corrections.get("documents", {}).get(key, {})))
    tracks = corrections.get("tasks", {}).get(task["task_id"])
    if tracks:
        task.setdefault("source", {}).update(copy.deepcopy(tracks))
        task["overview"]["is_umbrella"] = True


def correct_fulltext(task_id: str, pdf_url: str, text: str, corrections: dict | None = None) -> str:
    """Apply exact reviewed edits once; reject source drift instead of silently guessing."""
    if corrections is None:
        corrections = json.loads((CURATION_DIR / "fulltext_corrections.json").read_text())
    for edit in corrections.get(f"{task_id}|{pdf_url}", []):
        if edit["before"] in text:
            if text.count(edit["before"]) != 1:
                raise ValueError(f"ambiguous correction: {task_id} {pdf_url}")
            text = text.replace(edit["before"], edit["after"], 1)
        elif edit["after"] not in text:
            raise ValueError(f"correction source changed: {task_id} {pdf_url}")
    return text
