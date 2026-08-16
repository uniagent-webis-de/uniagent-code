#!/usr/bin/env python
"""Stage 4 — extract claimed team/run counts from overview PDFs, scoped to the 44
high-confidence task groups from Stage 3 (see PLAN.md section 3, Stage 4)."""
import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
PDF_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "pdf"
COUNTS_DIR = PROJECT_ROOT / "data" / "intermediate" / "counts"
LOGS_DIR = PROJECT_ROOT / "logs"

REQUEST_TIMEOUT_SECONDS = 30

# Restricting to the first ~15000 characters of extracted text (roughly the abstract,
# introduction, and any early results-summary paragraph for a typical CEUR paper) avoids
# picking up unrelated numbers from tables, results sections, or the bibliography further
# into longer overview papers.
SEARCH_WINDOW_CHARS = 15000

# Ordered by specificity: patterns naming *actual* participation ("received results
# from", "participating") are tried before a bare "N teams", because overview papers
# often report both a registration count and a (smaller) participation count in the same
# sentence — e.g. "98 teams registered ... we received results from 20 teams" — and only
# the latter is the correct denominator for coverage_ratio.
TEAM_PATTERNS = [
    re.compile(r"(\d+)\s+participating\s+teams", re.IGNORECASE),
    re.compile(r"received\s+(?:results|submissions)\s+from\s+(\d+)\s+teams", re.IGNORECASE),
    re.compile(r"(\d+)\s+teams\s+(?:actively\s+)?participat\w*", re.IGNORECASE),
    re.compile(r"(\d+)\s+teams\s+submitted", re.IGNORECASE),
    re.compile(r"total\s+of\s+(\d+)\s+teams", re.IGNORECASE),
    re.compile(r"(\d+)\s+teams\b(?!\s*(?:registered|up\b))", re.IGNORECASE),
]

# Team/run counts for a CLEF shared task are never in the hundreds-of-thousands, let
# alone four digits shaped like a year. Real bug found on CENTRE@CLEF 2019: "CENTRE@CLEF
# 2019 teams up with the Open-Source IR Replicability Challenge" used "teams" as a verb
# ("teams up with"), and the generic fallback pattern grabbed the adjacent year 2019 as
# if it were a team count. A negative lookahead for "up" fixes that specific phrasing,
# but a plausibility bound catches this whole class of error regardless of wording.
MAX_PLAUSIBLE_COUNT = 999


def is_plausible_count(n: int) -> bool:
    return 0 < n <= MAX_PLAUSIBLE_COUNT
RUN_PATTERNS = [
    re.compile(r"total\s+of\s+(\d+)\s+(?:valid\s+)?runs", re.IGNORECASE),
    re.compile(r"(\d+)\s+valid\s+runs", re.IGNORECASE),
    re.compile(r"(\d+)\s+runs\s+(?:were\s+)?submitted", re.IGNORECASE),
    re.compile(r"(\d+)\s+runs\b", re.IGNORECASE),
    re.compile(r"(\d+)\s+approaches", re.IGNORECASE),
]


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"extract_counts_{timestamp}.log"

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


def fetch_pdf(url: str, dest_path: Path, logger: logging.Logger) -> bool:
    if dest_path.exists():
        logger.info("cache hit: %s -> %s", url, dest_path)
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "uniagent-corpus-builder/0.1"})
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return False

    logger.info("fetched: %s status=%d -> %s", url, response.status_code, dest_path)
    if response.status_code != 200:
        logger.warning("non-200 status for %s: %d", url, response.status_code)
        return False

    dest_path.write_bytes(response.content)
    return True


def parse_pdf_text(pdf_path: Path, txt_path: Path, logger: logging.Logger) -> str | None:
    if txt_path.exists():
        logger.info("parse cache hit: %s", txt_path)
        return txt_path.read_text(encoding="utf-8")

    result = subprocess.run(
        ["lit", "parse", str(pdf_path), "--format", "text", "--no-ocr", "-o", str(txt_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("lit parse failed for %s: %s", pdf_path, result.stderr.strip())
        return None
    logger.info("parsed: %s -> %s", pdf_path, txt_path)
    return txt_path.read_text(encoding="utf-8")


NUMBERED_HEADING_RE = re.compile(r"\n(\d+)\.\s+\S")


def abstract_and_intro_window(text: str) -> str:
    """Restrict extraction to the abstract + introduction, ending at the start of the
    first numbered *task* subsection (typically "2. Task 1: ..."). Real bug found on
    eRisk 2023: without this boundary, a per-task participation sentence buried inside
    the Task 1 subsection ("37 runs from 10 participating teams") outscored the actual
    lab-wide total in the introduction ("received results from 20 teams") because it
    matched a higher-priority pattern — the section boundary must be checked first."""
    headings = list(NUMBERED_HEADING_RE.finditer(text))
    if len(headings) >= 2:
        return text[:headings[1].start()]
    return text[:SEARCH_WINDOW_CHARS]


RUNS_PER_TASK_RE = re.compile(r"(\d+)\s+runs\s+for\s+task\s*\d+", re.IGNORECASE)


def extract_run_count(window: str) -> int | None:
    """Some overviews report runs as an un-totaled per-task breakdown in the intro
    ("37 runs for Task 1, 48 runs for Task 2, and 20 runs for Task 3") rather than a
    single total. Sum that breakdown when found — a real case (eRisk 2023) otherwise
    silently yielded the first task's count (37) instead of the lab-wide total (105)."""
    per_task_matches = [int(n) for n in RUNS_PER_TASK_RE.findall(window)]
    plausible_per_task = [n for n in per_task_matches if is_plausible_count(n)]
    if len(plausible_per_task) >= 2:
        return sum(plausible_per_task)
    return extract_count(window, RUN_PATTERNS)


def extract_count(window: str, patterns: list[re.Pattern]) -> int | None:
    for pattern in patterns:
        for match in pattern.finditer(window):
            candidate = int(match.group(1))
            if is_plausible_count(candidate):
                return candidate
    return None


def process_task(task: dict, logger: logging.Logger) -> dict:
    task_id = task["task_id"]
    out_path = COUNTS_DIR / f"{task_id}.json"
    if out_path.exists():
        logger.info("counts cache hit: %s", out_path)
        return json.loads(out_path.read_text(encoding="utf-8"))

    pdf_dir = PDF_RAW_DIR / task_id
    pdf_path = pdf_dir / "overview.pdf"
    txt_path = pdf_dir / "overview.txt"

    if not fetch_pdf(task["overview"]["pdf_url"], pdf_path, logger):
        result = {"teams": None, "runs": None}
    else:
        text = parse_pdf_text(pdf_path, txt_path, logger)
        if text is None:
            result = {"teams": None, "runs": None}
        else:
            window = abstract_and_intro_window(text)
            teams = extract_count(window, TEAM_PATTERNS)
            runs = extract_run_count(window)

            # PLAN.md's own coverage_ratio bound doubles as a sanity check on the
            # extraction: more notebook papers than claimed teams (ratio > 1.5) means the
            # regex almost certainly grabbed the wrong number, e.g. a real case (LongEval
            # 2023) where "14 and 4 teams participated in Task 1 and Task 2, respectively"
            # yielded 4 (only the second, elliptically-written figure) against 14 actual
            # notebook papers. Null it out rather than keep a number known to be wrong.
            notebook_papers = len(task["participants"])
            if teams is not None and notebook_papers / teams > 1.5:
                logger.warning(
                    "%s: claimed teams=%d implausible against %d notebook papers (ratio %.2f > 1.5) — discarding as mis-parsed",
                    task_id, teams, notebook_papers, notebook_papers / teams,
                )
                teams = None

            result = {"teams": teams, "runs": runs}
            if teams is None:
                logger.warning("%s: no team-count pattern matched — storing null", task_id)
            if runs is None:
                logger.warning("%s: no run-count pattern matched — storing null", task_id)

    COUNTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract claimed team/run counts from overview PDFs.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to process (default: high only).")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("extract_counts")
    logger.info("logging to %s", log_path)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]

    matched_teams = matched_runs = 0
    for task in tasks:
        result = process_task(task, logger)
        if result["teams"] is not None:
            matched_teams += 1
        if result["runs"] is not None:
            matched_runs += 1

    logger.info(
        "processed %d tasks: team counts found for %d, run counts found for %d",
        len(tasks), matched_teams, matched_runs,
    )


if __name__ == "__main__":
    main()
