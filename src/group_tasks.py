#!/usr/bin/env python
"""Stage 3 — group each parsed section's papers into shared-task entries, linking one
overview paper to its participant/notebook papers. See PLAN.md section 3.

IMPORTANT DEVIATION FROM PLAN.MD, discovered while building this stage: PLAN.md's rule 1
("section grouping") assumes each overview paper is immediately followed by its own
participants until the next overview. Real CEUR-WS volumes instead front-load ALL of a
lab's overview papers first, then list participants in an order that is neither strictly
per-task nor alphabetical (verified across all 8 CLEF volumes). So for any section with
2+ overviews, title-keyword matching (PLAN.md's rule 3, "title_heuristic") is the primary
assignment mechanism here, not a rare last resort — and those groups are always written to
needs_review.jsonl with confidence="medium", never auto-promoted to the main corpus.
Sections with exactly one overview are unaffected: positional grouping is trivially
correct there and stays confidence="high".
"""
import argparse
import json
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECTIONS_DIR = PROJECT_ROOT / "data" / "intermediate" / "sections"
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "intermediate"
LOGS_DIR = PROJECT_ROOT / "logs"

OVERVIEW_TITLE_RE = re.compile(r"\boverview\b|\bextended abstract\b", re.IGNORECASE)
BEST_OF_LABS_RE = re.compile(r"\bbest of (the )?labs?\b", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or", "with",
    "overview", "task", "tasks", "lab", "labs", "extended", "abstract", "clef",
    # Generic shared-task/ML vocabulary. Real bug found reviewing Vol-2936 PAN: a "Hate
    # Speech Spreader Detection" paper (whose actual overview isn't published in this
    # volume at all) got routed into "Style Change Detection" purely because "detection"
    # was the only word it shared with any sibling overview, and — being section-locally
    # unique by chance — was scored as fully discriminative. These words describe the
    # shared-task *format*, not any specific task's topic, and recur across nearly every
    # CLEF lab regardless of subject, so they carry no assignment signal within a section.
    "detection", "classification", "identification", "prediction", "recognition",
    "analysis", "approach", "using", "based", "model", "models", "system", "systems",
    "method", "methods", "challenge", "evaluation", "text",
}


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"group_tasks_{timestamp}.log"

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


def tokenize(title: str) -> set[str]:
    # Split camelCase compounds (e.g. "BirdCLEF", "GeoLifeCLEF", "MedProcNER") before
    # lowercasing — otherwise "BirdCLEF" and "GeoLifeCLEF" collide as opaque single
    # tokens and only their shared, non-discriminative "CLEF" suffix would ever be
    # compared. "CLEF" itself still gets filtered out afterward via STOPWORDS.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    words = re.findall(r"[a-z0-9]+", spaced.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def extract_venue(lab_name: str) -> str:
    """Best-effort extraction of a short venue/lab acronym from a full section heading,
    e.g. "Overview of ... (BioASQ)" -> "BioASQ", "BioASQ: Large-scale ..." -> "BioASQ",
    "PAN Lab on Digital Text Forensics" -> "PAN". Falls back to the full heading when no
    recognizable pattern applies — imperfect but non-blocking; venue is a display field."""
    paren_match = re.search(r"\(([^()]+)\)\s*$", lab_name)
    if paren_match:
        return paren_match.group(1).strip()

    colon_match = re.match(r"^([^:]+):", lab_name)
    if colon_match:
        candidate = colon_match.group(1).strip()
        return re.sub(r"\s+Lab$", "", candidate, flags=re.IGNORECASE)

    dash_match = re.match(r"^([^-]+)-", lab_name)
    if dash_match:
        candidate = dash_match.group(1).strip()
        if candidate and " " not in candidate.strip("@"):
            return candidate

    first_word_match = re.match(r"^(\S+)\s+Lab\b", lab_name)
    if first_word_match:
        return first_word_match.group(1)

    return lab_name


def clean_task_name(overview_title: str) -> str:
    """Strip boilerplate ("Overview of the ...", trailing "at PAN 2023" / "in CLEF2023")
    from an overview title to produce a human-readable task name. Best-effort — see
    task_id, which only needs uniqueness, not cosmetic perfection."""
    title = overview_title.rstrip(".")

    marker = re.search(r"(overview|abstract) of (the )?", title, re.IGNORECASE)
    if marker:
        title = title[marker.end():]

    task_n = re.search(r"\bTask\s+\d+\s*[:\-]?\s*(on|of)?\s*", title, re.IGNORECASE)
    if task_n:
        remainder = title[task_n.end():].strip()
        if remainder:
            title = remainder

    title = re.sub(r"\s+(Task\s+)?(at|in)\s+.+$", "", title, flags=re.IGNORECASE)
    title = title.strip().rstrip(":").strip()
    return title or overview_title.rstrip(".")


def find_overview_indices(papers: list[dict], logger: logging.Logger, lab_name: str) -> list[int]:
    indices = [i for i, p in enumerate(papers) if OVERVIEW_TITLE_RE.search(p["title"])]
    if not indices and papers:
        logger.warning("no title matched overview keyword in section %r — using first paper as overview", lab_name)
        indices = [0]
    return indices


def split_best_of_labs(papers: list[dict], logger: logging.Logger) -> tuple[list[dict], list[dict]]:
    kept, excluded = [], []
    for p in papers:
        (excluded if BEST_OF_LABS_RE.search(p["title"]) else kept).append(p)
    if excluded:
        logger.info("excluded %d 'Best of Labs' re-publication paper(s)", len(excluded))
    return kept, excluded


def assign_by_position(papers: list[dict], overview_indices: list[int]) -> list[dict]:
    """Single-overview case: everything else in the section is that task's participants."""
    overview_idx = overview_indices[0]
    return [p for i, p in enumerate(papers) if i != overview_idx]


def assign_by_title_match(papers: list[dict], overview_indices: list[int], logger: logging.Logger, lab_name: str) -> dict[int, list[dict]]:
    """Multi-overview case: assign each participant to the overview whose title shares
    the most title-keyword weight with it. Each token is weighted 1/(number of overviews
    in this section containing it) — a token unique to one overview counts fully, a token
    shared by two related overviews (e.g. both GeoLifeCLEF and PlantCLEF mention "plant")
    still counts partially instead of being discarded outright. A hard "must be
    section-locally unique" cutoff was tried first and discarded real signal on any
    genuinely related pair of overviews, letting an unrelated one-off token collision
    (e.g. "Zero-Shot" vs "Few-Shot" both tokenizing to "shot") win by default."""
    overview_tokens = {i: tokenize(papers[i]["title"]) for i in overview_indices}
    token_counts: dict[str, int] = {}
    for tokens in overview_tokens.values():
        for tok in tokens:
            token_counts[tok] = token_counts.get(tok, 0) + 1
    token_weight = {tok: 1.0 / count for tok, count in token_counts.items()}

    assignments: dict[int, list[dict]] = {i: [] for i in overview_indices}
    overview_set = set(overview_indices)
    unassigned = 0

    tied = 0
    for i, paper in enumerate(papers):
        if i in overview_set:
            continue
        paper_tokens = tokenize(paper["title"])
        scores = {
            ov_i: sum(token_weight[tok] for tok in (paper_tokens & tokens))
            for ov_i, tokens in overview_tokens.items()
        }
        best_score = max(scores.values(), default=0)
        if best_score == 0:
            unassigned += 1
            continue
        best_overviews = [ov_i for ov_i, score in scores.items() if score == best_score]
        if len(best_overviews) > 1:
            # A genuine tie is worse than a zero score — resolving it arbitrarily (e.g.
            # via dict/max() iteration order) would silently invent an assignment with no
            # actual evidence behind it. Drop it, same as an unmatched paper.
            tied += 1
            continue
        assignments[best_overviews[0]].append(paper)

    if unassigned:
        logger.warning(
            "section %r: %d/%d participant papers could not be confidently matched to any overview by title keywords — dropped",
            lab_name, unassigned, len(papers) - len(overview_indices),
        )
    if tied:
        logger.warning(
            "section %r: %d/%d participant papers tied between 2+ overviews by title keyword score — dropped rather than guessed",
            lab_name, tied, len(papers) - len(overview_indices),
        )
    return assignments


TASK_NUMBER_RE = re.compile(r"\btask\s*(\d+)\b", re.IGNORECASE)


def declared_task_number(title: str) -> str | None:
    match = TASK_NUMBER_RE.search(title)
    return match.group(1) if match else None


def has_hidden_second_task(overview_title: str, participants: list[dict]) -> bool:
    """Real bug found reviewing CLEF eHealth 2021: a section had two real overview
    papers (SpRadIE Task 1 and Consumer Health Search Task 2), but the CHS one is titled
    "Consumer Health Search at CLEF eHealth 2021" — no "overview" or "extended abstract"
    anywhere — so find_overview_indices() missed it, leaving the section looking
    single-overview and "high confidence" when it wasn't. Positional grouping then dumped
    every CHS participant (and the CHS overview itself) under the SpRadIE task.

    The generalizable signal: when the *lone detected* overview explicitly names its own
    task number ("Overview of ... Task 1 - SpRadIE"), it is task-specific, not a lab-wide
    umbrella — so a "participant" declaring a *different* task number is real evidence of
    a second, undetected task, not just a subtask covered by this same overview. This does
    NOT fire on umbrella overviews with no task number of their own (verified against 6
    other CLEF labs — ChEMU, Touché, eRisk, MC2, QuantumCLEF — where participants
    routinely reference "Task 2" etc. as a subtask of one single all-encompassing
    overview; none of those overview titles declare their own task number)."""
    own_task = declared_task_number(overview_title)
    if own_task is None:
        return False
    return any(
        (p_task := declared_task_number(p["title"])) is not None and p_task != own_task
        for p in participants
    )


def group_section(section: dict, entry: dict, logger: logging.Logger, extracted_at: str) -> list[dict]:
    lab_name = section["lab_name"]
    papers, best_of_labs = split_best_of_labs(section["papers"], logger)
    if not papers:
        return []

    overview_indices = find_overview_indices(papers, logger, lab_name)
    tasks = []

    if len(overview_indices) == 1:
        overview = papers[overview_indices[0]]
        participants = assign_by_position(papers, overview_indices)
        if has_hidden_second_task(overview["title"], participants):
            logger.warning(
                "section %r: overview %r declares its own task number but a participant declares a different one — "
                "likely a second, undetected overview in this section; downgrading to confidence=medium for review",
                lab_name, overview["title"],
            )
            tasks.append(build_task_record(entry, lab_name, overview, participants, "section_grouping", "medium", extracted_at))
        else:
            tasks.append(build_task_record(entry, lab_name, overview, participants, "section_grouping", "high", extracted_at))
    else:
        assignments = assign_by_title_match(papers, overview_indices, logger, lab_name)
        for ov_idx in overview_indices:
            overview = papers[ov_idx]
            participants = assignments[ov_idx]
            tasks.append(build_task_record(entry, lab_name, overview, participants, "title_heuristic", "medium", extracted_at))

    rejected = [t for t in tasks if not t["participants"]]
    for t in rejected:
        logger.warning("rejecting task %r: 0 participants (PLAN.md pitfall 4)", t["task_id"])
    return [t for t in tasks if t["participants"]]


def build_task_record(entry: dict, lab_name: str, overview: dict, participants: list[dict], method: str, confidence: str, extracted_at: str) -> dict:
    venue = extract_venue(lab_name)
    task_name = clean_task_name(overview["title"])
    task_id = f"{entry['parent_venue'].lower()}{entry['year']}-{slugify(venue)}-{slugify(task_name)}"

    return {
        "task_id": task_id,
        "venue": venue,
        "parent_venue": entry["parent_venue"],
        "year": entry["year"],
        "task_name": task_name,
        "ceur_volume": entry["volume"],
        "overview": {
            "title": overview["title"],
            "pdf_url": overview["pdf_url"],
            "authors": overview["authors"],
            "is_umbrella": False,
        },
        "participants": [
            {
                "title": p["title"],
                "authors": p["authors"],
                "pdf_url": p["pdf_url"],
                "team_name": None,
                "code_urls": [],
                "tira_refs": [],
            }
            for p in participants
        ],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": method,
            "confidence": confidence,
            "extracted_at": extracted_at,
        },
    }


def validate(tasks: list[dict], logger: logging.Logger) -> None:
    task_ids = [t["task_id"] for t in tasks]
    duplicate_ids = {tid for tid in task_ids if task_ids.count(tid) > 1}
    if duplicate_ids:
        logger.error("duplicate task_id(s) found: %s", duplicate_ids)

    pdf_urls: dict[str, str] = {}
    for t in tasks:
        urls = [t["overview"]["pdf_url"]] + [p["pdf_url"] for p in t["participants"]]
        for url in urls:
            if url in pdf_urls and pdf_urls[url] != t["task_id"]:
                logger.error("duplicate pdf_url %s across tasks %s and %s (mis-grouped section?)", url, pdf_urls[url], t["task_id"])
            pdf_urls[url] = t["task_id"]

    for t in tasks:
        if not t["participants"]:
            logger.error("task %s has 0 participants — should have been rejected", t["task_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Group parsed sections into shared-task entries.")
    parser.add_argument("--volume", type=str, default=None, help="Group only this CEUR-WS volume number. Default: all parsed volumes.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("group_tasks")
    logger.info("logging to %s", log_path)

    section_files = sorted(SECTIONS_DIR.glob("*.json"))
    if args.volume is not None:
        section_files = [f for f in section_files if f.stem == args.volume]
        if not section_files:
            logger.error("no parsed section file for volume %s — run parse_sections.py first", args.volume)
            sys.exit(1)

    extracted_at = date.today().isoformat()
    all_tasks: list[dict] = []
    for section_file in section_files:
        data = json.loads(section_file.read_text(encoding="utf-8"))
        entry = {"parent_venue": data["parent_venue"], "year": data["year"], "volume": data["volume"]}
        for section in data["sections"]:
            all_tasks.extend(group_section(section, entry, logger, extracted_at))
        logger.info("volume %s: %d task groups so far", data["volume"], len(all_tasks))

    validate(all_tasks, logger)

    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    candidates_path = INTERMEDIATE_DIR / "all_candidates.jsonl"
    review_path = INTERMEDIATE_DIR / "needs_review.jsonl"

    with candidates_path.open("w", encoding="utf-8") as f:
        for task in all_tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")

    review_tasks = [t for t in all_tasks if t["provenance"]["confidence"] != "high"]
    with review_path.open("w", encoding="utf-8") as f:
        for task in review_tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")

    logger.info("wrote %d candidate tasks to %s (%d flagged for review in %s)", len(all_tasks), candidates_path, len(review_tasks), review_path)


if __name__ == "__main__":
    main()
