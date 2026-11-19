#!/usr/bin/env python
"""Assign legacy SemEval participant papers to tasks from their own first pages.

SemEval 2007-2015 participant papers have plain titles ("ECNU: Leveraging Word Embeddings...")
so the title carries no task number and ``collect_semeval`` cannot group them. Their first
pages usually name the task ("... SemEval-2015 Task 1"). This stage downloads each untitled
paper, reads its first two pages with ``pdftotext`` and records the task only when exactly one
task number of that year is named. Papers naming several tasks, or none, stay unassigned.

    python src/semeval_legacy_tasks.py --year 2015

Output: data/intermediate/semeval_task_evidence.json  {source_id: {...}}; ``collect_semeval``
reads it when present.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collect_semeval import RAW_DIR, parse_papers
from src.semeval_config import selected_volumes

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_PATH = PROJECT_ROOT / "data" / "intermediate" / "semeval_task_evidence.json"
PDF_DIR = RAW_DIR / "legacy_pdfs"
USER_AGENT = "uniagent-corpus-builder/0.2"
# "SemEval-2015 Task 1", "SemEval 2015, Task 10", "SemEval'15 Task 4", "Semeval-2012 shared task 6"
TASK_MENTION_RE = re.compile(
    r"s\s*em\s*e\s*val[\s\-–’'`]*(?P<year>(?:20)?\d\d)?[\s,:.\-–]*(?:shared\s+)?tasks?\s*#?(?P<num>\d{1,2})\b", re.IGNORECASE)
# "Task 1 of SemEval 2015", "task 10 at SemEval-2015", "Task1 of S EM E VAL-2015"
TASK_FIRST_RE = re.compile(
    r"tasks?\s*#?(?P<num>\d{1,2})\s*(?:\(|,)?\s*(?:of|at|in|for|from)\s+(?:the\s+)?s\s*em\s*e\s*val[\s\-–’'`]*(?P<year>(?:20)?\d\d)?",
    re.IGNORECASE)
LEGACY_YEARS = {2007, 2010, 2012, 2013, 2014, 2015}


def first_pages_text(pdf: Path, pages: int = 2) -> str:
    out = subprocess.run(["pdftotext", "-l", str(pages), str(pdf), "-"], capture_output=True, text=True)
    return re.sub(r"\s+", " ", out.stdout)


def task_numbers(text: str, year: int) -> list[int]:
    """Task numbers named for ``year`` (a mention without a year counts)."""
    found = set()
    for match in TASK_MENTION_RE.finditer(text):
        mention_year = match.group("year")
        if mention_year:
            mention_year = int(mention_year) + (2000 if int(mention_year) < 100 else 0)
        if mention_year in (None, year):
            found.add(int(match.group("num")))
    for match in TASK_FIRST_RE.finditer(text):
        mention_year = match.group("year")
        if mention_year:
            mention_year = int(mention_year) + (2000 if int(mention_year) < 100 else 0)
        if mention_year in (None, year):
            found.add(int(match.group("num")))
    return sorted(found)


def flag_order_conflicts(evidence: dict) -> None:
    """Proceedings list a task's papers together. An assigned paper whose task differs from
    both neighbouring assigned papers, when those agree with each other, is more likely a
    paper that merely cites another task, so it is withheld (``order_conflict``)."""
    for year in {v["year"] for v in evidence.values()}:
        ids = sorted(k for k, v in evidence.items() if v["year"] == year and v["status"] in ("assigned", "order_conflict"))
        tasks = [evidence[k]["task_numbers"][0] for k in ids]
        for i, key in enumerate(ids):
            if 0 < i < len(ids) - 1 and tasks[i - 1] == tasks[i + 1] != tasks[i]:
                evidence[key]["status"] = "order_conflict"
            elif evidence[key]["status"] == "order_conflict":
                evidence[key]["status"] = "assigned"


def download(url: str, path: Path) -> bool:
    if path.exists():
        return True
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except requests.RequestException:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    time.sleep(0.5)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    evidence = json.loads(EVIDENCE_PATH.read_text()) if EVIDENCE_PATH.exists() else {}
    for volume in selected_volumes(args.year):
        if volume["year"] not in LEGACY_YEARS:
            continue
        papers = parse_papers((RAW_DIR / f"{volume['collection_id']}.html").read_text(encoding="utf-8"), volume)
        todo = [p for p in papers if p["task_number"] is None and p["pdf_url"] and not p["source_id"].endswith("000")]
        print(f"{volume['year']}: {len(todo)} untitled papers", flush=True)
        for paper in todo:
            if paper["source_id"] in evidence:
                continue
            pdf = PDF_DIR / f"{paper['source_id']}.pdf"
            if not download(paper["pdf_url"], pdf):
                evidence[paper["source_id"]] = {"year": volume["year"], "status": "download_failed"}
                continue
            numbers = task_numbers(first_pages_text(pdf), volume["year"])
            status = "assigned" if len(numbers) == 1 else "ambiguous" if numbers else "none"
            evidence[paper["source_id"]] = {"year": volume["year"], "status": status, "task_numbers": numbers}
            EVIDENCE_PATH.write_text(json.dumps(evidence, indent=1))
    flag_order_conflicts(evidence)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=1))
    from collections import Counter
    print(Counter((v["year"], v["status"]) for v in evidence.values()))


if __name__ == "__main__":
    main()
