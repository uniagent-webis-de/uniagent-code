#!/usr/bin/env python
"""Assemble the final benchmark deliverables from the high-confidence candidate tasks,
joined with Stage 4 counts and Stage 5 code links. See PLAN.md sections 1, 5, 6."""
import argparse
import csv
import json
import logging
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
COUNTS_DIR = PROJECT_ROOT / "data" / "intermediate" / "counts"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
FINAL_DIR = PROJECT_ROOT / "data" / "final"
LOGS_DIR = PROJECT_ROOT / "logs"

CSV_FIELDS = [
    "task_id", "venue", "parent_venue", "year", "task_name", "ceur_volume",
    "overview_title", "overview_pdf_url", "overview_authors", "is_umbrella",
    "notebook_papers", "teams_claimed_in_overview", "runs_claimed_in_overview", "coverage_ratio",
    "participant_pdf_urls", "code_urls", "tira_refs",
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
        # Final schema (PLAN.md section 1) stores code_urls as a flat URL list. A dead
        # link is still evidence the team had a repo, so it's kept — not filtered by
        # its validated HTTP status, which lives only in the intermediate file.
        participant["code_urls"] = [c["url"] for c in entry["code_urls"]]
        participant["tira_refs"] = entry["tira_refs"]


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
                "code_urls": "; ".join(all_code_urls),
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

    lines += [
        "",
        "## Coverage",
        "",
        f"- Total participant/notebook papers: {total_participants}",
        f"- Tasks with a known coverage_ratio: {len(ratios)}/{len(tasks)}",
        f"- Mean coverage_ratio (where known): {round(sum(ratios) / len(ratios), 3) if ratios else 'n/a'}",
        "",
        "## Code links",
        "",
        f"- Participant papers with at least one resolved code/TIRA link: {with_code}/{total_participants}",
        f"- Participant papers with no resolved link: {unresolved}/{total_participants}",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble final shared_tasks.jsonl / .csv / report.md from high-confidence candidate tasks.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to include (default: high only).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for the spot-check sample.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("build_corpus")
    logger.info("logging to %s", log_path)
    random.seed(args.seed)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]
    logger.info("assembling corpus from %d tasks (confidence=%s)", len(tasks), args.confidence)

    for task in tasks:
        join_counts(task, logger)
        join_code_links(task, logger)

    if not validate(tasks, logger):
        logger.error("validation failed — see errors above. Deliverables NOT written.")
        sys.exit(1)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(tasks, FINAL_DIR / "shared_tasks.jsonl")
    write_csv(tasks, FINAL_DIR / "shared_tasks.csv")
    write_report(tasks, FINAL_DIR / "report.md")
    logger.info("wrote %d tasks to data/final/shared_tasks.jsonl, .csv, report.md", len(tasks))


if __name__ == "__main__":
    main()
