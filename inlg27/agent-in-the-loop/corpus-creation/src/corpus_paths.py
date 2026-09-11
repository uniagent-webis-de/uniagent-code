"""Canonical paths for the Phase 1 shared-task corpus layout.

The corpus builder keeps source caches and intermediate records under ``data`` while
placing each accepted task's PDFs and parsed assets together under ``data/final``.
Keeping path construction here prevents the download, parsing, and enrichment stages
from drifting apart as the layout evolves.
"""

import re
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
CANDIDATES_DIR = INTERMEDIATE_DIR / "candidates"
SCREENING_DIR = INTERMEDIATE_DIR / "screening"
FINAL_DIR = DATA_DIR / "final"
MANIFEST_PATH = FINAL_DIR / "manifest.jsonl"


def paper_id_for(pdf_url: str) -> str:
    """Return the stable, filesystem-safe paper id used inside a task directory."""
    stem = Path(urlparse(pdf_url).path).stem
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", stem) or "paper"


def task_dir(task_id: str) -> Path:
    return FINAL_DIR / task_id


def overview_dir(task_id: str) -> Path:
    return task_dir(task_id) / "overview"


def participant_dir(task_id: str, pdf_url: str) -> Path:
    return task_dir(task_id) / "papers" / paper_id_for(pdf_url)


def document_dir(task_id: str, role: str, pdf_url: str) -> Path:
    if role == "overview":
        return overview_dir(task_id)
    if role == "participant":
        return participant_dir(task_id, pdf_url)
    raise ValueError(f"unsupported document role: {role}")


def document_pdf_path(task_id: str, role: str, pdf_url: str) -> Path:
    directory = document_dir(task_id, role, pdf_url)
    filename = "overview.pdf" if role == "overview" else "paper.pdf"
    return directory / filename


def document_markdown_path(task_id: str, role: str, pdf_url: str) -> Path:
    directory = document_dir(task_id, role, pdf_url)
    filename = "overview.txt.md" if role == "overview" else "paper.txt.md"
    return directory / filename


def document_figures_dir(task_id: str, role: str, pdf_url: str) -> Path:
    return document_dir(task_id, role, pdf_url) / "figures"


def document_tables_dir(task_id: str, role: str, pdf_url: str) -> Path:
    return document_dir(task_id, role, pdf_url) / "tables"


def task_metadata_path(task_id: str) -> Path:
    return task_dir(task_id) / "metadata.json"


def overview_pdf_path(task_id: str) -> Path:
    return document_pdf_path(task_id, "overview", "")


def overview_markdown_path(task_id: str) -> Path:
    return document_markdown_path(task_id, "overview", "")


def participant_pdf_path(task_id: str, pdf_url: str) -> Path:
    return document_pdf_path(task_id, "participant", pdf_url)


def participant_markdown_path(task_id: str, pdf_url: str) -> Path:
    return document_markdown_path(task_id, "participant", pdf_url)
