#!/usr/bin/env python
"""Stage 9 — assemble the final benchmark deliverables from enriched candidate tasks."""
import argparse
import csv
import json
import logging
import random
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.paper_links import document_links
from src.task_field import field_for
from src.corpus_paths import (
    FINAL_DIR,
    MANIFEST_PATH,
    document_figures_dir,
    document_markdown_path,
    document_pdf_path,
    document_tables_dir,
    paper_id_for,
    participant_dir,
    task_dir,
    task_metadata_path,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
COUNTS_DIR = PROJECT_ROOT / "data" / "intermediate" / "counts"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
# Authors read from a paper's first page where the source listed none: {"task_id|pdf_url": [names]}.
# Every name was checked against the page text before it was stored.
AUTHORS_EXTRACTED_PATH = PROJECT_ROOT / "data" / "intermediate" / "authors_extracted.json"
FULLTEXT_MANIFEST_PATH = MANIFEST_PATH
LOGS_DIR = PROJECT_ROOT / "logs"

CSV_FIELDS = [
    "task_id", "venue", "parent_venue", "year", "field", "task_name", "ceur_volume",
    "overview_title", "overview_pdf_url", "overview_authors", "is_umbrella",
    "notebook_papers", "teams_claimed_in_overview", "runs_claimed_in_overview", "coverage_ratio",
    "participant_pdf_urls", "team_names", "overview_pdf_path", "participant_pdf_paths",
    "overview_fulltext_path", "participant_fulltext_paths",
    "code_urls", "code_urls_live", "code_urls_likely_own", "tira_refs",
    "task_assignment_method", "confidence", "extracted_at",
]


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"build_corpus_{timestamp}.log"

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


def join_counts(task: dict, logger: logging.Logger) -> None:
    counts_path = COUNTS_DIR / f"{task['task_id']}.json"
    teams = runs = None
    if counts_path.exists():
        data = json.loads(counts_path.read_text(encoding="utf-8"))
        teams, runs = data.get("teams"), data.get("runs")
    else:
        logger.warning("%s: no counts file found — coverage_ratio will be null", task["task_id"])

    notebook_papers = len(task["participants"])
    coverage_ratio = round(notebook_papers / teams, 3) if teams else None

    task["counts"] = {
        "notebook_papers": notebook_papers,
        "teams_claimed_in_overview": teams,
        "runs_claimed_in_overview": runs,
        "coverage_ratio": coverage_ratio,
    }


def join_code_links(task: dict, logger: logging.Logger) -> None:
    code_path = CODE_DIR / f"{task['task_id']}.json"
    if not code_path.exists():
        logger.warning("%s: no code-links file found — code_urls/tira_refs left empty", task["task_id"])
        return

    by_pdf_url = {entry["pdf_url"]: entry for entry in json.loads(code_path.read_text(encoding="utf-8"))}
    for participant in task["participants"]:
        entry = by_pdf_url.get(participant["pdf_url"])
        if entry is None:
            continue
        # PLAN.md section 1 keeps code_urls a flat URL list. A dead link is still evidence
        # the team had a repo, so nothing is filtered by HTTP status — but the status and
        # the code-availability evidence are carried alongside in code_url_details so a
        # consumer can tell a live repo from a 404 or an unverified rate-limited check
        # without re-fetching every link.
        participant["code_urls"] = [c["url"] for c in entry["code_urls"]]
        participant["code_url_details"] = [
            {
                "url": c["url"], "status": c["status"], "availability_evidence": c.get("evidence", False),
                "own_code_score": c.get("own_code_score"), "likely_own_code": c.get("likely_own_code"),
            }
            for c in entry["code_urls"]
        ]
        participant["third_party_urls"] = entry.get("third_party_urls", [])
        participant["tira_refs"] = entry["tira_refs"]


def join_extracted_authors(task: dict, extracted: dict) -> None:
    """Fill empty ``authors`` from first-page extraction and record where they came from."""
    for document in [task["overview"], *task["participants"]]:
        if document.get("authors"):
            document["authors_source"] = "source_metadata"
            continue
        names = extracted.get(f"{task['task_id']}|{document['pdf_url']}")
        document["authors"] = names or []
        document["authors_source"] = "extracted_from_text" if names else None


def join_links(task: dict) -> None:
    """Attach ``links`` (code, dataset, model, TIRA) to the overview and every participant,
    read from each document's parsed text. Needs ``fulltext_path``, so run after
    join_fulltext_paths."""
    for document in [task["overview"], *task["participants"]]:
        path = document.get("fulltext_path")
        text = (PROJECT_ROOT / path).read_text(encoding="utf-8") if path else ""
        scores = {d["url"]: d.get("own_code_score") for d in document.get("code_url_details", [])}
        document["links"] = document_links(text, scores)


def write_paper_links(tasks: list[dict], path: Path) -> None:
    """One row per link: task_id, document (overview|participant), pdf_url, then the link."""
    with path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            for role, document in [("overview", task["overview"])] + [("participant", p) for p in task["participants"]]:
                for link in document.get("links", []):
                    row = {"task_id": task["task_id"], "document": role, "pdf_url": document["pdf_url"], **link}
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def join_fulltext_paths(task: dict, manifest: dict, logger: logging.Logger) -> None:
    """Publish each document's parsed-markdown path on the record itself, so consumers can
    go from a corpus entry straight to its text without deriving filenames from URLs."""
    if not manifest:
        return

    def apply(document: dict, record: dict | None) -> None:
        document["pdf_path"] = record.get("pdf_path") if record else None
        document["fulltext_path"] = record["markdown_path"] if record else None
        # "ocr" text (scanned or garbled PDFs) is lower fidelity: words can be displaced and
        # columns interleaved, so consumers can filter on this.
        document["text_source"] = "ocr" if record and record.get("ocr_server_used") else "text_layer"
        document["ocr_engine"] = record.get("ocr_engine") if record else None
        document["figures_dir"] = record.get("figures_dir") if record else None
        document["n_figures"] = record.get("n_figures", 0) if record else 0
        document["pdffigures2_status"] = record.get("pdffigures2_status") if record else None
        document["pdffigures2_figures"] = record.get("pdffigures2_figures", 0) if record else 0
        document["pdffigures2_tables"] = record.get("pdffigures2_tables", 0) if record else 0
        document["tables_dir"] = record.get("tables_dir") if record else None
        document["n_tables"] = record.get("n_tables", 0) if record else 0

    def lookup(pdf_url: str) -> dict | None:
        # Manifests are keyed by (task_id, pdf_url).  The URL-only fallback keeps this
        # helper compatible with older manifests and unit fixtures.
        return manifest.get((task["task_id"], pdf_url)) or manifest.get(pdf_url)

    overview_record = lookup(task["overview"]["pdf_url"])
    apply(task["overview"], overview_record)
    if overview_record is None:
        logger.warning("%s: overview has no parsed full text", task["task_id"])

    missing = 0
    for participant in task["participants"]:
        record = lookup(participant["pdf_url"])
        apply(participant, record)
        if record is None:
            missing += 1
    if missing:
        logger.warning("%s: %d/%d participants have no parsed full text", task["task_id"], missing, len(task["participants"]))


def load_fulltext_manifest(logger: logging.Logger) -> dict:
    """Map (task_id, pdf_url) -> parsed-document record from the full-text manifest."""
    if not FULLTEXT_MANIFEST_PATH.exists():
        logger.warning("no full-text manifest at %s — run parse_fulltext.py to add fulltext_path fields", FULLTEXT_MANIFEST_PATH)
        return {}
    manifest = {}
    for line in FULLTEXT_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        key = (record.get("task_id"), record["pdf_url"])
        manifest[key] = record
        # Preserve URL-only lookup for older records that lack task-specific paths.
        manifest.setdefault(record["pdf_url"], record)
    logger.info("loaded full-text manifest with %d documents", len(manifest))
    return manifest


NON_PAPER_NAME_RE = re.compile(r"poster|slides|sample|(?:^|[-_])(?:topics?|formalrun\w*|fmlrun\w*)(?:[-_.]|$)|-inv-", re.IGNORECASE)
NON_PAPER_TITLE_RE = re.compile(r"^(?:full list\b|\d{4}(?:-\d{2,4})? document sets?\b)", re.IGNORECASE)
MIN_PAPER_CHARS = 3000  # below this a PDF is an abstract / one-pager, not a working-note paper


def is_non_paper(record: dict | None) -> bool:
    """True for abstract-only (1 page or <3000 chars), poster, slide, or sample PDFs.

    Two-page papers are legitimate (MediaEval, TREC notebooks), so page count alone is
    not the signal; thin extracted text is, after OCR has had its chance."""
    if record is None:
        return False
    name = record["pdf_url"].rsplit("/", 1)[-1]
    return (
        record["pages"] <= 1 or record["chars"] < MIN_PAPER_CHARS
        or bool(NON_PAPER_NAME_RE.search(name))
    )


# Papers filed as a task's "overview" that are really a participant's paper (found in the
# quality review): CEUR holds no organizer overview for these CLEF editions, so the tasks
# have no overview paper and are dropped.
PARTICIPANT_PAPERS_FILED_AS_OVERVIEW = frozenset({
    "https://ceur-ws.org/Vol-1167/CLEF2001wn-adhoc-Savoy2001.pdf",
    "https://ceur-ws.org/Vol-1169/CLEF2003wn-adhoc-Savoy2003.pdf",
})

DROPPED_PATH = FINAL_DIR / "dropped_documents.jsonl"


def load_dropped() -> set[tuple[str, str]]:
    """(task_id, pdf_url) pairs dropped by earlier builds. Their files are deleted and the
    manifest forgets them, so the decision must be remembered to stay repeatable."""
    if not DROPPED_PATH.exists():
        return set()
    rows = (json.loads(line) for line in DROPPED_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    return {(r["task_id"], r["pdf_url"]) for r in rows}


def save_dropped(dropped: list[tuple[str, str, str]], previous: set[tuple[str, str]]) -> None:
    pairs = previous | {(tid, url) for tid, _, url in dropped}
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    DROPPED_PATH.write_text(
        "".join(json.dumps({"task_id": tid, "pdf_url": url}) + "\n" for tid, url in sorted(pairs)), encoding="utf-8"
    )


def prune_unreferenced(tasks: list[dict], logger: logging.Logger) -> None:
    """Make data/final mirror the corpus: delete paper folders no participant references
    (dropped, re-assigned, or empty leftovers from older filename slugs) and remove
    manifest records of documents that are no longer in the corpus."""
    expected_docs = set()
    for task in tasks:
        expected_docs.add((task["task_id"], task["overview"]["pdf_url"]))
        expected_docs |= {(task["task_id"], p["pdf_url"]) for p in task["participants"]}
        keep = {participant_dir(task["task_id"], p["pdf_url"]).name for p in task["participants"]}
        papers = task_dir(task["task_id"]) / "papers"
        for path in sorted(papers.iterdir()) if papers.is_dir() else []:
            if path.is_dir() and path.name not in keep:
                logger.warning("pruning unreferenced paper folder %s", path)
                shutil.rmtree(path)
    if MANIFEST_PATH.exists():
        rows = [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        kept = [r for r in rows if (r.get("task_id"), r["pdf_url"]) in expected_docs]
        if len(kept) != len(rows):
            logger.warning("pruned %d manifest record(s) for documents not in the corpus", len(rows) - len(kept))
            MANIFEST_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")


def drop_non_papers(tasks: list[dict], manifest: dict, logger: logging.Logger, previously_dropped: frozenset | set = frozenset()) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Remove non-paper participants; drop tasks whose overview is a non-paper or that
    have fewer than 2 real participant papers (the corpus floor). Returns (kept, dropped) where
    dropped holds (task_id, role, pdf_url) — a dropped task lists all its documents."""
    kept, dropped = [], []
    for task in tasks:
        tid = task["task_id"]

        def lookup(url: str) -> dict | None:
            return manifest.get((tid, url)) or manifest.get(url)

        def non_paper(doc: dict) -> bool:
            url = doc["pdf_url"]
            return (tid, url) in previously_dropped or is_non_paper(lookup(url)) or bool(NON_PAPER_TITLE_RE.search(doc["title"]))

        bad = [p for p in task["participants"] if non_paper(p)]
        if task["overview"]["pdf_url"] in PARTICIPANT_PAPERS_FILED_AS_OVERVIEW:
            reason = "the filed overview is a participant paper (no organizer overview exists)"
        elif non_paper(task["overview"]):
            reason = "overview is not a full paper"
        elif len(task["participants"]) - len(bad) < 2:
            reason = "fewer than 2 real participant papers"
        else:
            reason = None
        if reason:
            logger.warning("dropping task %s: %s", tid, reason)
            dropped += [(tid, "overview", task["overview"]["pdf_url"])] + [(tid, "participant", p["pdf_url"]) for p in task["participants"]]
            continue
        for p in bad:
            logger.warning("%s: dropping non-paper participant %s", tid, p["pdf_url"])
            dropped.append((tid, "participant", p["pdf_url"]))
        task["participants"] = [p for p in task["participants"] if p not in bad]
        kept.append(task)
    return kept, dropped


CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def selection_key(task: dict) -> tuple:
    """PLAN.md section 3 Stage 6 ranking: coverage_ratio descending, then high confidence
    before medium, then non-umbrella before umbrella, then more participants first.

    A null coverage_ratio means the overview's team count was not extractable, so it
    sorts below every known ratio rather than being treated as a zero or a perfect score."""
    ratio = task["counts"]["coverage_ratio"]
    return (
        0 if ratio is not None else 1,
        -(ratio if ratio is not None else 0),
        CONFIDENCE_RANK.get(task["provenance"]["confidence"], 9),
        1 if task["overview"]["is_umbrella"] else 0,
        -len(task["participants"]),
    )


def select_corpus(tasks: list[dict], target: int | None, logger: logging.Logger) -> list[dict]:
    """Rank candidates and optionally emit only the top ``target``.

    With no target, every candidate selected by the confidence filter is emitted. The
    selection is a view, not a destructive filter — every candidate remains in
    ``all_candidates.jsonl``.
    """
    ranked = sorted(tasks, key=selection_key)
    if target is not None and len(ranked) > target:
        logger.info("selecting top %d of %d ranked candidates", target, len(ranked))
        return ranked[:target]
    if target is None:
        logger.info("no target cap configured; emitting all %d candidates, ranked", len(ranked))
    else:
        logger.info("all %d candidates are within the target of %d; emitting all, ranked", len(ranked), target)
    return ranked


def validate(tasks: list[dict], logger: logging.Logger) -> bool:
    ok = True

    for task in tasks:
        if not task["participants"]:
            logger.error("VALIDATION FAILED: %s has 0 participants", task["task_id"])
            ok = False

    task_ids = [t["task_id"] for t in tasks]
    duplicate_ids = {tid for tid in task_ids if task_ids.count(tid) > 1}
    if duplicate_ids:
        logger.error("VALIDATION FAILED: duplicate task_id(s): %s", duplicate_ids)
        ok = False

    pdf_urls: dict[str, tuple[str, dict]] = {}
    for t in tasks:
        documents = [t["overview"], *t["participants"]]
        for document in documents:
            url = document["pdf_url"]
            if url in pdf_urls and pdf_urls[url][0] != t["task_id"]:
                logger.error("VALIDATION FAILED: duplicate pdf_url %s across %s and %s", url, pdf_urls[url][0], t["task_id"])
                ok = False
            pdf_urls[url] = (t["task_id"], document)

    for t in tasks:
        ratio = t["counts"]["coverage_ratio"]
        if ratio is not None and not (0 <= ratio <= 1.5):
            logger.error("VALIDATION FAILED: %s coverage_ratio=%.3f outside [0, 1.5]", t["task_id"], ratio)
            ok = False

    sample = random.sample(tasks, min(5, len(tasks)))
    logger.info("--- spot-check sample (%d tasks) ---", len(sample))
    for t in sample:
        logger.info("%s", t["task_id"])
        logger.info("  overview: %s", t["overview"]["title"])
        for p in t["participants"][:5]:
            logger.info("    - %s", p["title"])
        if len(t["participants"]) > 5:
            logger.info("    ... and %d more", len(t["participants"]) - 5)

    return ok


def validate_output_files(tasks: list[dict], logger: logging.Logger) -> bool:
    """Ensure the final records point to the local PDF and Markdown files."""
    ok = True
    for task in tasks:
        documents = [("overview", task["overview"]["pdf_url"])]
        documents.extend(("participant", p["pdf_url"]) for p in task["participants"])
        for role, pdf_url in documents:
            pdf_path = document_pdf_path(task["task_id"], role, pdf_url)
            markdown_path = document_markdown_path(task["task_id"], role, pdf_url)
            if not pdf_path.exists():
                logger.error("VALIDATION FAILED: missing PDF %s", pdf_path)
                ok = False
            if not markdown_path.exists():
                logger.error("VALIDATION FAILED: missing Markdown %s", markdown_path)
                ok = False
            figures_dir = document_figures_dir(task["task_id"], role, pdf_url)
            tables_dir = document_tables_dir(task["task_id"], role, pdf_url)
            if not figures_dir.is_dir():
                logger.error("VALIDATION FAILED: missing figures directory %s", figures_dir)
                ok = False
            if not tables_dir.is_dir():
                logger.error("VALIDATION FAILED: missing tables directory %s", tables_dir)
                ok = False
    return ok


def validate_final_task_directories(tasks: list[dict], logger: logging.Logger) -> bool:
    """Ensure ``data/final`` contains exactly the tasks being assembled.

    The downloader promotes complete task trees transactionally. This check catches
    stale or partial directories that could otherwise look like corpus records to a
    consumer even though they are absent from ``shared_tasks.jsonl``.
    """
    expected = {task["task_id"] for task in tasks}
    actual = {
        path.name
        for path in FINAL_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    } if FINAL_DIR.exists() else set()

    ok = True
    for task_id in sorted(expected - actual):
        logger.error("VALIDATION FAILED: missing final task directory %s", FINAL_DIR / task_id)
        ok = False
    for task_id in sorted(actual - expected):
        logger.error("VALIDATION FAILED: unexpected final task directory %s", FINAL_DIR / task_id)
        ok = False
    return ok


def write_task_metadata(task: dict) -> None:
    path = task_metadata_path(task["task_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Each document's links also sit next to its PDF and text, as ``links.json`` (only when it has any).
    for document in [task["overview"], *task["participants"]]:
        if document.get("fulltext_path"):
            folder = (PROJECT_ROOT / document["fulltext_path"]).parent
            links_path = folder / "links.json"
            if document.get("links"):  # an empty file would only add noise
                links_path.write_text(json.dumps(document["links"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                links_path.unlink(missing_ok=True)


def write_subtask_indexes(task: dict) -> None:
    """Write ``subtasks/task-<n>.json`` listing the papers of each sub-task.

    Umbrella tasks (one overview covering several sub-tasks, e.g. SISAP) store each
    paper once under ``papers/``; these small indexes show which papers belong to
    which sub-task without copying papers that address several sub-tasks.
    """
    subtasks_dir = task_dir(task["task_id"]) / "subtasks"
    shutil.rmtree(subtasks_dir, ignore_errors=True)
    subtasks = task.get("source", {}).get("subtasks")
    if not subtasks:
        return
    subtasks_dir.mkdir(parents=True)
    for subtask in subtasks:
        papers = [
            {
                "paper_dir": f"papers/{paper_id_for(paper['pdf_url'])}",
                "team_name": paper.get("team_name"),
                "title": paper["title"],
            }
            for paper in task["participants"]
            if str(subtask["number"]) in {str(number) for number in paper.get("task_numbers", [])}
        ]
        index = {
            "task_id": task["task_id"],
            "subtask": subtask["number"],
            "name": subtask["name"],
            "overview_dir": "overview",
            "papers": papers,
        }
        (subtasks_dir / f"task-{str(subtask['number']).lower()}.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def write_jsonl(tasks: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def write_summary_csv(tasks: list[dict], path: Path) -> None:
    """Short per-task listing: name, source, year, notebook papers, and where it was sourced."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["task_id", "name", "source", "year", "field", "notebook_papers", "source_url", "task_page_url"])
        for t in sorted(tasks, key=lambda t: (t["parent_venue"], t["year"], t["task_name"])):
            src = t["source"]
            page = src.get("track_url") or src.get("official_url") or src.get("toc_url") or src.get("tasks_url") or ""
            writer.writerow([t["task_id"], t["task_name"], t["parent_venue"], t["year"], t["field"],
                             len(t["participants"]), src["proceedings_url"], page])


def write_csv(tasks: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for t in tasks:
            all_code_urls = sorted({u for p in t["participants"] for u in p["code_urls"]})
            live_code_urls = sorted({
                d["url"] for p in t["participants"] for d in p.get("code_url_details", [])
                if d["status"] == "200"
            })
            likely_own_urls = sorted({
                d["url"] for p in t["participants"] for d in p.get("code_url_details", [])
                if d["status"] == "200" and d.get("likely_own_code")
            })
            team_names = sorted({p["team_name"] for p in t["participants"] if p["team_name"]})
            all_tira_refs = sorted({r for p in t["participants"] for r in p["tira_refs"]})
            writer.writerow({
                "task_id": t["task_id"],
                "venue": t["venue"],
                "parent_venue": t["parent_venue"],
                "year": t["year"],
                "field": t["field"],
                "task_name": t["task_name"],
                "ceur_volume": t["ceur_volume"],
                "overview_title": t["overview"]["title"],
                "overview_pdf_url": t["overview"]["pdf_url"],
                "overview_authors": "; ".join(t["overview"]["authors"]),
                "is_umbrella": t["overview"]["is_umbrella"],
                "notebook_papers": t["counts"]["notebook_papers"],
                "teams_claimed_in_overview": t["counts"]["teams_claimed_in_overview"],
                "runs_claimed_in_overview": t["counts"]["runs_claimed_in_overview"],
                "coverage_ratio": t["counts"]["coverage_ratio"],
                "participant_pdf_urls": "; ".join(p["pdf_url"] for p in t["participants"]),
                "team_names": "; ".join(team_names),
                "overview_pdf_path": t["overview"].get("pdf_path") or "",
                "participant_pdf_paths": "; ".join(p.get("pdf_path") or "" for p in t["participants"]),
                "overview_fulltext_path": t["overview"].get("fulltext_path") or "",
                # Positionally aligned with participant_pdf_urls; empty where unparsed.
                "participant_fulltext_paths": "; ".join(p.get("fulltext_path") or "" for p in t["participants"]),
                "code_urls": "; ".join(all_code_urls),
                "code_urls_live": "; ".join(live_code_urls),
                "code_urls_likely_own": "; ".join(likely_own_urls),
                "tira_refs": "; ".join(all_tira_refs),
                "task_assignment_method": t["provenance"]["task_assignment_method"],
                "confidence": t["provenance"]["confidence"],
                "extracted_at": t["provenance"]["extracted_at"],
            })


def write_report(tasks: list[dict], path: Path) -> None:
    by_venue_year = Counter((t["parent_venue"], t["year"]) for t in tasks)
    ratios = [t["counts"]["coverage_ratio"] for t in tasks if t["counts"]["coverage_ratio"] is not None]
    total_participants = sum(len(t["participants"]) for t in tasks)
    with_code = sum(1 for t in tasks for p in t["participants"] if p["code_urls"] or p["tira_refs"])
    unresolved = total_participants - with_code

    lines = [
        "# Shared-Task Corpus Report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Total tasks: {len(tasks)}",
        "",
        "## Tasks per venue/year",
        "",
        "| Parent venue | Year | Tasks |",
        "|---|---|---|",
    ]
    for (venue, year), count in sorted(by_venue_year.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines.append(f"| {venue} | {year} | {count} |")

    umbrella = sum(1 for t in tasks if t["overview"]["is_umbrella"])
    named_teams = sum(1 for t in tasks for p in t["participants"] if p["team_name"])
    details = [d for t in tasks for p in t["participants"] for d in p.get("code_url_details", [])]
    live = sum(1 for d in details if d["status"] == "200")
    dead = sum(1 for d in details if d["status"] in {"404", "unreachable"})
    unverified = sum(1 for d in details if d["status"] == "429")
    evidenced = sum(1 for d in details if d["availability_evidence"])
    third_party = sum(len(p.get("third_party_urls", [])) for t in tasks for p in t["participants"])

    lines += [
        "",
        "## Coverage",
        "",
        f"- Total participant/notebook papers: {total_participants}",
        f"- Tasks with a known coverage_ratio: {len(ratios)}/{len(tasks)}",
        f"- Mean coverage_ratio (where known): {round(sum(ratios) / len(ratios), 3) if ratios else 'n/a'}",
        f"- Umbrella overviews (one overview serving several sub-tasks): {umbrella}/{len(tasks)}",
        f"- Participants with an extracted team_name: {named_teams}/{total_participants}",
        "",
        "`coverage_ratio` is null where the overview's claimed team count could not be",
        "extracted; those entries sort last in the ranking rather than being scored.",
        "",
        "## Code links",
        "",
        f"- Participant papers with at least one resolved code/TIRA link: {with_code}/{total_participants}",
        f"- Participant papers with no resolved link: {unresolved}/{total_participants}",
        "",
        f"- Code URLs stored: {len(details)} (live 200: {live}, dead 404/unreachable: {dead}, unverified 429 rate-limited: {unverified})",
        f"- Of those, backed by an explicit code-availability statement: {evidenced}",
        f"- Third-party dependency URLs excluded from code_urls: {third_party}",
        "",
        "Links are not filtered by HTTP status: a dead repository is still evidence the",
        "team published code. Use `code_url_details[].status` to distinguish, and",
        "`availability_evidence` to prefer links the authors explicitly released.",
        "Dependencies the team merely used (transformers, nltk, pretrained weights) are",
        "kept out of `code_urls` and listed per participant in `third_party_urls`.",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble final shared_tasks.jsonl / .csv / report.md from high-confidence candidate tasks.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to include (default: high only).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for the spot-check sample.")
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Optional maximum number of tasks to emit; by default all selected candidates are emitted.",
    )
    parser.add_argument("--task-id", type=str, default=None, help="Assemble only this task id.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("build_corpus")
    logger.info("logging to %s", log_path)
    random.seed(args.seed)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.task_id is not None:
        tasks = [task for task in tasks if task["task_id"] == args.task_id]
        if not tasks:
            logger.error("task_id %s not found", args.task_id)
            sys.exit(1)
    elif args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]
    logger.info("assembling corpus from %d tasks (confidence=%s)", len(tasks), args.confidence)

    fulltext_manifest = load_fulltext_manifest(logger)
    strict_layout = args.task_id is None and args.target is None and args.confidence == "high"
    if fulltext_manifest:
        previously_dropped = load_dropped()
        tasks, dropped = drop_non_papers(tasks, fulltext_manifest, logger, previously_dropped)
        logger.info("dropped %d non-paper document(s); %d tasks remain", len(dropped), len(tasks))
        if strict_layout:  # final/ must mirror the corpus, so remove what was dropped
            save_dropped(dropped, previously_dropped)
            kept_ids = {t["task_id"] for t in tasks}
            for tid, role, url in dropped:
                shutil.rmtree(task_dir(tid) if tid not in kept_ids else document_pdf_path(tid, role, url).parent, ignore_errors=True)
    extracted_authors = json.loads(AUTHORS_EXTRACTED_PATH.read_text(encoding="utf-8")) if AUTHORS_EXTRACTED_PATH.exists() else {}
    for task in tasks:
        task["field"] = field_for(task["parent_venue"], task["task_name"])
        join_counts(task, logger)
        join_code_links(task, logger)
        join_fulltext_paths(task, fulltext_manifest, logger)
        join_links(task)
        join_extracted_authors(task, extracted_authors)

    tasks = select_corpus(tasks, args.target, logger)

    if strict_layout:
        prune_unreferenced(tasks, logger)
    layout_ok = validate_final_task_directories(tasks, logger) if strict_layout else True
    if not validate(tasks, logger) or not validate_output_files(tasks, logger) or not layout_ok:
        logger.error("validation failed — see errors above. Deliverables NOT written.")
        sys.exit(1)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        write_task_metadata(task)
        write_subtask_indexes(task)
    write_jsonl(tasks, FINAL_DIR / "shared_tasks.jsonl")
    write_csv(tasks, FINAL_DIR / "shared_tasks.csv")
    write_summary_csv(tasks, FINAL_DIR / "shared_tasks_summary.csv")
    write_paper_links(tasks, FINAL_DIR / "paper_links.jsonl")
    write_report(tasks, FINAL_DIR / "report.md")
    logger.info("wrote %d tasks to data/final/shared_tasks.jsonl, .csv, report.md", len(tasks))


if __name__ == "__main__":
    main()
