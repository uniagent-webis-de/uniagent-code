#!/usr/bin/env python
"""Stage 9 — assemble the final benchmark deliverables from enriched candidate tasks."""
import argparse
import csv
import json
import logging
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import (
    FINAL_DIR,
    MANIFEST_PATH,
    document_figures_dir,
    document_markdown_path,
    document_pdf_path,
    document_tables_dir,
    task_metadata_path,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
COUNTS_DIR = PROJECT_ROOT / "data" / "intermediate" / "counts"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
FULLTEXT_MANIFEST_PATH = MANIFEST_PATH
LOGS_DIR = PROJECT_ROOT / "logs"

CSV_FIELDS = [
    "task_id", "venue", "parent_venue", "year", "task_name", "ceur_volume",
    "overview_title", "overview_pdf_url", "overview_authors", "is_umbrella",
    "notebook_papers", "teams_claimed_in_overview", "runs_claimed_in_overview", "coverage_ratio",
    "participant_pdf_urls", "team_names", "overview_pdf_path", "participant_pdf_paths",
    "overview_fulltext_path", "participant_fulltext_paths",
    "code_urls", "code_urls_live", "tira_refs",
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
            {"url": c["url"], "status": c["status"], "availability_evidence": c.get("evidence", False)}
            for c in entry["code_urls"]
        ]
        participant["third_party_urls"] = entry.get("third_party_urls", [])
        participant["tira_refs"] = entry["tira_refs"]


def join_fulltext_paths(task: dict, manifest: dict[str, dict], logger: logging.Logger) -> None:
    """Publish each document's parsed-markdown path on the record itself, so consumers can
    go from a corpus entry straight to its text without deriving filenames from URLs."""
    if not manifest:
        return

    def apply(document: dict, record: dict | None) -> None:
        document["pdf_path"] = record.get("pdf_path") if record else None
        document["fulltext_path"] = record["markdown_path"] if record else None
        document["figures_dir"] = record.get("figures_dir") if record else None
        document["n_figures"] = record.get("n_figures", 0) if record else 0
        document["pdffigures2_status"] = record.get("pdffigures2_status") if record else None
        document["pdffigures2_figures"] = record.get("pdffigures2_figures", 0) if record else 0
        document["pdffigures2_tables"] = record.get("pdffigures2_tables", 0) if record else 0
        document["tables_dir"] = record.get("tables_dir") if record else None
        document["n_tables"] = record.get("n_tables", 0) if record else 0

    overview_record = manifest.get(task["overview"]["pdf_url"])
    apply(task["overview"], overview_record)
    if overview_record is None:
        logger.warning("%s: overview has no parsed full text", task["task_id"])

    missing = 0
    for participant in task["participants"]:
        record = manifest.get(participant["pdf_url"])
        apply(participant, record)
        if record is None:
            missing += 1
    if missing:
        logger.warning("%s: %d/%d participants have no parsed full text", task["task_id"], missing, len(task["participants"]))


def load_fulltext_manifest(logger: logging.Logger) -> dict[str, dict]:
    """Map pdf_url -> parsed-document record from the full-text manifest."""
    if not FULLTEXT_MANIFEST_PATH.exists():
        logger.warning("no full-text manifest at %s — run parse_fulltext.py to add fulltext_path fields", FULLTEXT_MANIFEST_PATH)
        return {}
    manifest = {}
    for line in FULLTEXT_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        manifest[record["pdf_url"]] = record
    logger.info("loaded full-text manifest with %d documents", len(manifest))
    return manifest


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

    pdf_urls: dict[str, str] = {}
    for t in tasks:
        urls = [t["overview"]["pdf_url"]] + [p["pdf_url"] for p in t["participants"]]
        for url in urls:
            if url in pdf_urls and pdf_urls[url] != t["task_id"]:
                logger.error("VALIDATION FAILED: duplicate pdf_url %s across %s and %s", url, pdf_urls[url], t["task_id"])
                ok = False
            pdf_urls[url] = t["task_id"]

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


def write_task_metadata(task: dict) -> None:
    path = task_metadata_path(task["task_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(tasks: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


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
            team_names = sorted({p["team_name"] for p in t["participants"] if p["team_name"]})
            all_tira_refs = sorted({r for p in t["participants"] for r in p["tira_refs"]})
            writer.writerow({
                "task_id": t["task_id"],
                "venue": t["venue"],
                "parent_venue": t["parent_venue"],
                "year": t["year"],
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
    for task in tasks:
        join_counts(task, logger)
        join_code_links(task, logger)
        join_fulltext_paths(task, fulltext_manifest, logger)

    tasks = select_corpus(tasks, args.target, logger)

    if not validate(tasks, logger) or not validate_output_files(tasks, logger):
        logger.error("validation failed — see errors above. Deliverables NOT written.")
        sys.exit(1)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        write_task_metadata(task)
    write_jsonl(tasks, FINAL_DIR / "shared_tasks.jsonl")
    write_csv(tasks, FINAL_DIR / "shared_tasks.csv")
    write_report(tasks, FINAL_DIR / "report.md")
    logger.info("wrote %d tasks to data/final/shared_tasks.jsonl, .csv, report.md", len(tasks))


if __name__ == "__main__":
    main()
