#!/usr/bin/env python
"""Stage 5 — resolve participant code links, scoped to the 44 high-confidence task
groups from Stage 3 (see PLAN.md section 3, Stage 5)."""
import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
PDF_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "pdf"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
LOGS_DIR = PROJECT_ROOT / "logs"

REQUEST_TIMEOUT_SECONDS = 30
HEAD_TIMEOUT_SECONDS = 10

CODE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.[a-z0-9.\-]+|zenodo\.org/record|huggingface\.co)/\S+",
    re.IGNORECASE,
)
TIRA_URL_RE = re.compile(r"https?://(?:www\.)?tira\.io/\S+", re.IGNORECASE)
TIRA_DOCKER_RE = re.compile(r"\bdocker\.io/[\w\-./:]+", re.IGNORECASE)

# Trailing punctuation that's part of the surrounding sentence, not the URL itself
# (e.g. "see https://github.com/x/y." at the end of a sentence).
TRAILING_PUNCTUATION_RE = re.compile(r"[.,;:)\]]+$")

# A paper's bibliography cites the tools it used; those are not the team's own code.
# PLAN.md Stage 5 says code links live in a footnote or a "Reproducibility"/"Availability"
# section, so everything from the reference list onward is dropped before matching.
REFERENCES_HEADING_RE = re.compile(r"(?im)^[ \t]*(?:\d+\.?\s*)?(references|bibliography|works cited)[ \t]*$")

# Namespaces that publish the field's shared infrastructure and pretrained weights. A URL
# under one of these is a dependency the team *used*, never the code the team *wrote*.
# Audit found these made up ~48% of stored code_urls, so the field misrepresented
# ubiquitous libraries (transformers, nltk, keras, trec_eval) as team submissions.
THIRD_PARTY_NAMESPACES = {
    "huggingface", "pytorch", "tensorflow", "keras", "fchollet", "scikit-learn", "scipy",
    "numpy", "pandas-dev", "explosion", "nltk", "facebookresearch", "facebookai", "facebook",
    "meta-llama", "google", "google-research", "google-bert", "googlecreativelab", "microsoft",
    "openai", "allenai", "ukplab", "sentence-transformers", "cardiffnlp", "castorini",
    "usnistgov", "fasterxml", "rare-technologies", "stanfordnlp", "flairnlp", "deepset-ai",
    "deepset", "mistralai", "qwen", "bigscience", "eleutherai", "tiiuae", "intfloat", "baai",
    "sentencepiece", "apache", "elastic", "terrier-org", "terrierteam", "explosion-ai",
    "spacy-io", "dmlc", "xgboost", "unslothai", "langchain-ai", "jina-ai", "nomic-ai",
    "salesforce", "databricks", "mosaicml", "togethercomputer", "thudm", "internlm",
    "openai-community", "datasets", "sebastianruder", "zenodo",
}

# Hugging Face paths are frequently a bare pretrained-model name with no org segment
# (e.g. huggingface.co/bert-base-uncased) — also a dependency, not team code.
BARE_MODEL_NAME_RE = re.compile(
    r"^(bert|roberta|distilbert|albert|xlm|xlnet|gpt2|gpt-2|t5|flan|deberta|electra|bart|mbart|mt5|opt|bloom|llama)[\w.\-]*$",
    re.IGNORECASE,
)

# Phrases that mark a link as the authors' own released artifact rather than a passing
# mention. Recorded as evidence so a consumer can prefer high-signal links.
CODE_AVAILABILITY_RE = re.compile(
    r"(our code|source code|code is available|code are available|code can be found|is available at|are available at|"
    r"we release|publicly available|made available|reproducib|our implementation|our repository|"
    r"github repository|our system is available|we provide the code|implementation is available)",
    re.IGNORECASE,
)
OWNER_RE = re.compile(r"^https?://(?:www\.)?(?:github\.com|gitlab\.[^/]+|huggingface\.co|zenodo\.org)/([^/\s?#]+)", re.IGNORECASE)


def strip_bibliography(text: str) -> str:
    """Drop the reference list. Uses the last heading found, and only when it sits past
    the first third of the document, so an in-body mention of the word "references"
    does not truncate the paper."""
    matches = list(REFERENCES_HEADING_RE.finditer(text))
    if not matches:
        return text
    last = matches[-1]
    if last.start() < len(text) * 0.3:
        return text
    return text[: last.start()]


def is_third_party(url: str) -> bool:
    match = OWNER_RE.match(url)
    if not match:
        return False
    owner = match.group(1).lower()
    return owner in THIRD_PARTY_NAMESPACES or bool(BARE_MODEL_NAME_RE.match(owner))


def has_availability_evidence(text: str, position: int) -> bool:
    """Look at the sentence-ish window around the URL for a code-release phrase."""
    window = text[max(0, position - 240) : position + 120]
    return bool(CODE_AVAILABILITY_RE.search(window))


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"find_code_{timestamp}.log"

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


def clean_url(url: str) -> str:
    return TRAILING_PUNCTUATION_RE.sub("", url)


def extract_links(text: str) -> tuple[list[dict], list[str], list[str]]:
    """Return (candidate_code_links, third_party_urls, tira_refs) from a paper's text.

    Candidates are the links plausibly pointing at the team's own artifact: found outside
    the bibliography and not under a known third-party namespace. Each carries an
    `evidence` flag recording whether it appeared in a code-availability context.
    Third-party URLs are returned separately rather than discarded, so the exclusion stays
    auditable instead of silently dropping data."""
    body = strip_bibliography(text)

    candidates: dict[str, bool] = {}
    third_party: set[str] = set()
    for match in CODE_URL_RE.finditer(body):
        url = clean_url(match.group(0))
        if not url:
            continue
        if is_third_party(url):
            third_party.add(url)
            continue
        evidence = has_availability_evidence(body, match.start())
        candidates[url] = candidates.get(url, False) or evidence

    tira_refs = sorted(
        {clean_url(u) for u in TIRA_URL_RE.findall(body)}
        | {clean_url(u) for u in TIRA_DOCKER_RE.findall(body)}
    )
    candidate_links = [{"url": u, "evidence": candidates[u]} for u in sorted(candidates)]
    return candidate_links, sorted(third_party), tira_refs


def validate_url(url: str, logger: logging.Logger) -> str:
    """HEAD-check a code URL. Returns a status label; a dead link is kept (not dropped)
    since per PLAN.md it's still evidence the team had a repo."""
    try:
        response = requests.head(url, timeout=HEAD_TIMEOUT_SECONDS, allow_redirects=True, headers={"User-Agent": "uniagent-corpus-builder/0.1"})
        status = str(response.status_code)
    except requests.RequestException as exc:
        status = "unreachable"
        logger.warning("HEAD check failed for %s: %s", url, exc)
    logger.info("code URL check: %s -> %s", url, status)
    return status


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


def pdf_filename_for(pdf_url: str) -> str:
    stem = Path(urlparse(pdf_url).path).stem
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)


def process_participant(task_id: str, participant: dict, logger: logging.Logger) -> dict:
    pdf_url = participant["pdf_url"]
    stem = pdf_filename_for(pdf_url)
    pdf_dir = PDF_RAW_DIR / task_id
    pdf_path = pdf_dir / f"{stem}.pdf"
    txt_path = pdf_dir / f"{stem}.txt"

    empty = {"pdf_url": pdf_url, "code_urls": [], "third_party_urls": [], "tira_refs": []}
    if not fetch_pdf(pdf_url, pdf_path, logger):
        return empty

    text = parse_pdf_text(pdf_path, txt_path, logger)
    if text is None:
        return empty

    candidates, third_party, tira_refs = extract_links(text)
    if third_party:
        logger.info("%s: excluded %d third-party dependency link(s)", pdf_url, len(third_party))
    if not candidates and not tira_refs:
        logger.info("%s: no code links found", pdf_url)
        return {"pdf_url": pdf_url, "code_urls": [], "third_party_urls": third_party, "tira_refs": tira_refs}

    validated = [
        {"url": c["url"], "status": validate_url(c["url"], logger), "evidence": c["evidence"]}
        for c in candidates
    ]
    return {"pdf_url": pdf_url, "code_urls": validated, "third_party_urls": third_party, "tira_refs": tira_refs}


def process_task(task: dict, logger: logging.Logger) -> list[dict]:
    task_id = task["task_id"]
    out_path = CODE_DIR / f"{task_id}.json"
    if out_path.exists():
        logger.info("code cache hit: %s", out_path)
        return json.loads(out_path.read_text(encoding="utf-8"))

    results = [process_participant(task_id, p, logger) for p in task["participants"]]

    CODE_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve participant code links for candidate tasks.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to process (default: high only).")
    parser.add_argument("--task-id", type=str, default=None, help="Process only this single task_id (for testing).")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("find_code")
    logger.info("logging to %s", log_path)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.task_id is not None:
        tasks = [t for t in tasks if t["task_id"] == args.task_id]
    elif args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]

    total_participants = 0
    with_code = 0
    for task in tasks:
        results = process_task(task, logger)
        total_participants += len(results)
        with_code += sum(1 for r in results if r["code_urls"] or r["tira_refs"])
        logger.info("%s: %d/%d participants have a resolved link", task["task_id"], sum(1 for r in results if r["code_urls"] or r["tira_refs"]), len(results))

    logger.info("processed %d tasks, %d participant papers: %d have at least one resolved code/TIRA link", len(tasks), total_participants, with_code)


if __name__ == "__main__":
    main()
