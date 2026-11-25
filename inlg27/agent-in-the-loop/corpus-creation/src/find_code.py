#!/usr/bin/env python
"""Stage 8 — resolve participant code links from parsed Markdown."""
import argparse
import hashlib
import json
import logging
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import paper_id_for, participant_markdown_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
CODE_DIR = PROJECT_ROOT / "data" / "intermediate" / "code"
LOGS_DIR = PROJECT_ROOT / "logs"

HEAD_TIMEOUT_SECONDS = 10

# The body is Markdown, so a URL ends at a link delimiter ( ] ) > " ` | ), not just whitespace.
CODE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.[a-z0-9.\-]+|zenodo\.org/records?|huggingface\.co)/[^\s\])>\"'<`|{}\\]*",
    re.IGNORECASE,
)
# liteparse renders PDF hyperlinks as ``[visible text](href)``. The visible text is often
# chopped by line wrapping while the href is complete, so the href is authoritative.
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(<?\s*(https?://[^)\s>]+)\s*>?\)")
MARKDOWN_ESCAPE_RE = re.compile(r"\\([_*#\[\]()<>`~|])")
# huggingface.co paths that are documentation, not a model/dataset/space repository.
HF_NON_REPO = {"transformers", "docs", "blog", "models", "datasets", "spaces", "learn", "papers", "tasks", "api", "join", "pricing"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
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


# ---------------------------------------------------------------------------------------
# Own-code scoring. A link in a paper is not necessarily the team's own code (it may be a
# library, a pretrained model, or the organizers' data). Each link gets a probability from
# a small logistic model over transparent features. The weights were fitted on 170 links
# whose repository README and paper context were judged by hand; 5-fold cross-validation,
# re-weighted to the full population of live links, gave about 91% precision and 86% recall
# at the 0.7 threshold (the older `evidence` flag alone: 91% / 38%). The labelled sample is
# small, so treat these as estimates, not guarantees.
# ---------------------------------------------------------------------------------------
OWN_PHRASE_RE = re.compile(
    r"(our|we)\W+(\w+\W+){0,3}(code|implementation|system|source|repositor|release|open.?sourc|publish|share|provid)"
    r"|(code|codes|implementation|source|system|models?|scripts?|data)\W+(\w+\W+){0,4}(is|are|can be|will be|has been|have been)\W+"
    r"(\w+\W+){0,3}(available|released|found|open.?sourced|public|shared|published|provided)"
    r"|open.?sourced?|publicly available|available (at|on|in|under)|code\s*[:\u2021\u2020*]|github\s*:|repository|repo\b|reproduc",
    re.IGNORECASE,
)
BORROW_RE = re.compile(
    r"based on|following|pre-?trained|(we|were|was) (use|used|using|adopt|adopted|utili[sz]e|borrow)|provided by|baseline|"
    r"organi[sz]er|official|toolkit|library|package|implementation of|tool\b|tools\b|thankful|starting point|original|"
    r"from the authors|built (on|upon)",
    re.IGNORECASE,
)
REFLINE_RE = re.compile(
    r"arxiv|cite arxiv|proceedings of|\bpp\.|et al\.|\bin:|\bjournal\b|\(\d{4}\)\.|\b(19|20)\d\d\.\s|conference on|association for",
    re.IGNORECASE,
)
DATA_CONTEXT_RE = re.compile(
    r"data ?sets?\b|leaderboard|evaluation|scorer|corpus|benchmark|provided|test set|training set", re.IGNORECASE
)
VENUE_WORDS = ("semeval", "clef", "ntcir", "trec", "fire", "hasoc", "wassa", "mediaeval", "sisap", "conll", "shared", "competition", "challenge", "task", "track")
TITLE_STOPWORDS = frozenset("task shared challenge track system systems detection analysis using based language models model for the and of in on to with from at".split())

# Logistic weights (see above). A feature missing from a link (e.g. README unknown) is simply 0.
LINK_WEIGHTS = {
    "name_venue": 0.3, "name_year": 0.8, "name_task": 1.0, "own_phrase": 0.8, "own_phrase_near": 1.0,
    "borrow": -0.7, "refline": -0.2, "rd_venue": 0.7, "rd_task": 0.2, "rd_year": 0.7, "rd_title": 0.6,
    "rd_pkg": -0.25, "rd_org": -0.1, "rd_empty": 1.0, "pa_match": 1.0, "ov_match": -0.5, "ctx_data": -0.3,
}
LINK_INTERCEPT = -2.07
OWN_CODE_THRESHOLD = 0.7
README_DIR = PROJECT_ROOT / "data" / "intermediate" / "readmes"


def _content_tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 4 and w not in TITLE_STOPWORDS]


def _last_names(authors: list[str]) -> set[str]:
    """First and last name tokens (>=4 letters) of an author list, lowercased."""
    names: set[str] = set()
    for author in authors or []:
        for part in re.split(r"[,;]| and ", author):
            tokens = [t for t in re.findall(r"[A-Za-z\u00c0-\u00ff'\-]+", part) if len(t) >= 4]
            if tokens:
                names.update({tokens[0].lower(), tokens[-1].lower()})
    return names


def link_features(url: str, before: str, after: str, readme: str | None, task: dict, paper: dict) -> dict[str, bool]:
    """Boolean features of one candidate link. ``readme`` is None when it could not be read
    (unsupported host, dead link): README features then stay False instead of guessing."""
    owner_repo = url.split("://", 1)[1].split("/", 1)[1].lower()
    squashed = owner_repo.replace("-", "").replace("_", "")
    owner = owner_repo.split("/")[0].replace("-", "").replace("_", "")
    venue, year = str(task["parent_venue"]).lower(), str(task["year"])
    task_tokens = set(_content_tokens(task["task_name"])) | set(_content_tokens(paper["title"]))
    near = before[-140:] + after[:60]
    paper_match = any(n in owner for n in _last_names(paper.get("authors")))
    f = {
        "name_venue": any(w in owner_repo for w in (venue, *VENUE_WORDS)),
        "name_year": year in owner_repo or year[2:] in re.findall(r"\d+", owner_repo),
        "name_task": any(t in squashed for t in task_tokens),
        "own_phrase": bool(OWN_PHRASE_RE.search(before + after)),
        "own_phrase_near": bool(OWN_PHRASE_RE.search(near)),
        "borrow": bool(BORROW_RE.search(before[-170:] + after[:50])),
        "refline": bool(REFLINE_RE.search(before + after)),
        "pa_match": paper_match,
        "ov_match": any(n in owner for n in _last_names(task["overview"].get("authors"))) and not paper_match,
        "ctx_data": bool(DATA_CONTEXT_RE.search(before[-120:] + after[:50])),
    }
    rl = (readme or "").lower()
    known = readme is not None
    f.update({
        "rd_venue": known and bool(rl) and bool(re.search(re.escape(venue), rl) or re.search(r"shared task|challenge|competition|track", rl)),
        "rd_task": known and sum(t in rl for t in task_tokens) >= 2,
        "rd_year": known and year in rl,
        "rd_title": known and sum(t in rl for t in _content_tokens(paper["title"])) >= 3,
        "rd_pkg": known and bool(re.search(r"pip install|pypi|conda install", rl)),
        "rd_org": known and bool(re.search(r"organi[sz]ers?|starter|baseline|official (scor|eval)|evaluation script", rl[:1500])),
        "rd_empty": known and len(rl.strip()) < 80,
    })
    return f


def own_code_probability(features: dict[str, bool]) -> float:
    """Probability that a link is the paper's own code, from the logistic weights."""
    logit = LINK_INTERCEPT + sum(weight for name, weight in LINK_WEIGHTS.items() if features.get(name))
    return 1.0 / (1.0 + math.exp(-logit))


_README_CACHE: dict[str, str | None] = {}


def _readme_urls(url: str) -> list[str]:
    path = url.split("://", 1)[1].split("/", 1)[1]
    if url.startswith("https://github.com/"):
        base = f"https://raw.githubusercontent.com/{path}/HEAD/"
        return [base + name for name in ("README.md", "readme.md", "README.rst", "README.txt", "README")]
    if url.startswith("https://huggingface.co/"):
        return [f"https://huggingface.co/{path}/raw/main/README.md"]
    return []


def fetch_readme(url: str) -> str | None:
    """First ~4000 characters of a repository README, '' if the repo has none, None when the
    host is unsupported or the network failed. Cached on disk, one file per URL."""
    if url in _README_CACHE:
        return _README_CACHE[url]
    candidates = _readme_urls(url)
    if not candidates:
        return None
    cache_file = README_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
    else:
        text, failed = "", False
        for candidate in candidates:
            try:
                response = requests.get(candidate, timeout=HEAD_TIMEOUT_SECONDS, headers=HEADERS)
            except requests.RequestException:
                failed = True
                break
            if response.status_code == 200:
                text = response.text[:4000]
                break
            if response.status_code in RETRY_STATUSES:
                failed = True
                break
        if failed:
            _README_CACHE[url] = None
            return None
        README_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    _README_CACHE[url] = text
    return text


def fetch_readmes_all(urls: set[str]) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch_readme, sorted(urls)))


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


def canonical_repo_url(url: str) -> str | None:
    """Reduce a matched URL to the repository it names, or None when it names no
    repository (a bare profile/org, a docs page, a truncated or malformed link).

    https, no ``www``, no ``.git``, and no deep path (``/tree/main/...``), so the same
    repository found in different spellings is stored once."""
    url = clean_url(url)
    match = re.match(r"https?://(?:www\.)?([^/]+)/(.*)$", url, re.IGNORECASE)
    if not match:
        return None
    host, path = match.group(1).lower(), match.group(2)
    segments = [seg for seg in re.split(r"[/?#]", path.split("/-/")[0]) if seg]
    if host == "zenodo.org":
        return f"https://zenodo.org/records/{segments[1]}" if len(segments) >= 2 and segments[1].isdigit() else None
    if host == "huggingface.co":
        if not segments or segments[0] in HF_NON_REPO and segments[0] not in {"datasets", "spaces"}:
            return None
        depth = 3 if segments[0] in {"datasets", "spaces"} else 2
        segments = segments[:depth]
        if len(segments) < depth:
            return None
    elif host == "github.com" or host.startswith("gitlab."):
        # GitLab project paths may nest in subgroups; cut at the first web-UI segment.
        for i, seg in enumerate(segments):
            if seg in {"tree", "blob", "issues", "pull", "pulls", "wiki", "releases", "commit", "commits", "raw"} and i >= 2:
                segments = segments[:i]
                break
        if host == "github.com":
            segments = segments[:2]
        if len(segments) < 2:
            return None
    else:
        return None
    segments[-1] = re.sub(r"\.git$", "", segments[-1])
    if not all(NAME_RE.match(seg) for seg in segments):
        return None
    return f"https://{host}/" + "/".join(segments)


def rejoin_fenced_urls(text: str) -> str:
    """Repair PDF footnote URLs wrapped after a URL separator, inside code fences only."""
    def repair(match: re.Match) -> str:
        return re.sub(
            r"(https?://(?:github\.com|huggingface\.co|gitlab\.[a-z0-9.-]+)/[^\s`]*[_/-])\n[ \t]*([A-Za-z0-9_.-]+)(?=\n)",
            r"\1\2", match.group(0),
        )
    return re.sub(r"```[^\n]*\n.*?\n```", repair, text, flags=re.DOTALL)


def extract_links(text: str) -> tuple[list[dict], list[str], list[str]]:
    """Return (candidate_code_links, third_party_urls, tira_refs) from a paper's text.

    Candidates are the links plausibly pointing at the team's own artifact: found outside
    the bibliography and not under a known third-party namespace. Each carries an
    `evidence` flag recording whether it appeared in a code-availability context.
    Third-party URLs are returned separately rather than discarded, so the exclusion stays
    auditable instead of silently dropping data."""
    body = strip_bibliography(text)
    body = MARKDOWN_LINK_RE.sub(r" \1 ", body)
    body = MARKDOWN_ESCAPE_RE.sub(r"\1", body)
    body = rejoin_fenced_urls(body)

    candidates: dict[str, dict] = {}
    third_party: set[str] = set()
    for match in CODE_URL_RE.finditer(body):
        url = canonical_repo_url(match.group(0))
        if not url:
            continue
        if is_third_party(url):
            third_party.add(url)
            continue
        evidence = has_availability_evidence(body, match.start())
        seen = candidates.get(url)
        # Keep the occurrence that carries availability evidence (else the first one) as
        # the context the own-code score reads.
        if seen is None or (evidence and not seen["evidence"]):
            candidates[url] = {
                "evidence": evidence,
                "before": body[max(0, match.start() - 260):match.start()],
                "after": body[match.end():match.end() + 110],
            }

    tira_refs = sorted(
        {clean_url(u) for u in TIRA_URL_RE.findall(body)}
        | {clean_url(u) for u in TIRA_DOCKER_RE.findall(body)}
    )
    # A link cut off by line wrapping ("…/semeval26_task10_") is superseded by the full URL
    # when the same paper also contains it (usually as the Markdown href).
    for url in list(candidates):
        if url.endswith(("-", "_")) and any(other != url and other.startswith(url) for other in candidates):
            del candidates[url]
    candidate_links = [{"url": u, **candidates[u]} for u in sorted(candidates)]
    return candidate_links, sorted(third_party), tira_refs


_STATUS_CACHE: dict[str, str] = {}
HEADERS = {"User-Agent": "uniagent-corpus-builder/0.1"}
RETRY_STATUSES = {403, 405, 429, 500, 502, 503, 504}


def validate_url(url: str, logger: logging.Logger) -> str:
    """Check a code URL once. HEAD first, then GET for servers that reject HEAD; rate
    limits (429) are retried with backoff. A dead link is kept (not dropped) since per
    PLAN.md it's still evidence the team had a repo — the status says which it is."""
    if url in _STATUS_CACHE:
        return _STATUS_CACHE[url]
    status = "unreachable"
    for attempt in range(5):
        try:
            response = requests.head(url, timeout=HEAD_TIMEOUT_SECONDS, allow_redirects=True, headers=HEADERS)
            if response.status_code in RETRY_STATUSES:
                response = requests.get(url, timeout=HEAD_TIMEOUT_SECONDS, allow_redirects=True, headers=HEADERS, stream=True)
                response.close()
            status = str(response.status_code)
        except requests.RequestException as exc:
            status = "unreachable"
            logger.warning("check failed for %s: %s", url, exc)
        if status not in {str(c) for c in RETRY_STATUSES}:
            break
        time.sleep(2 ** (attempt + 1))
    logger.info("code URL check: %s -> %s", url, status)
    _STATUS_CACHE[url] = status
    return status


def load_known_statuses() -> None:
    """Seed the cache with definitive results (200/404) from an earlier run, so a re-run
    after an extraction fix only network-checks the URLs it has not seen."""
    for path in CODE_DIR.glob("*.json"):
        for result in json.loads(path.read_text(encoding="utf-8")):
            for link in result["code_urls"]:
                if link["status"] in {"200", "404"}:
                    _STATUS_CACHE.setdefault(link["url"], link["status"])


def validate_all(urls: set[str], logger: logging.Logger) -> None:
    """Warm the status cache for many URLs concurrently (each URL is checked once)."""
    pending = [u for u in sorted(urls) if u not in _STATUS_CACHE]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda u: validate_url(u, logger), pending))


def pdf_filename_for(pdf_url: str) -> str:
    """Backward-compatible name for the canonical paper-id helper."""
    return paper_id_for(pdf_url)


def process_participant(task_id: str, participant: dict, logger: logging.Logger, task: dict | None = None) -> dict:
    pdf_url = participant["pdf_url"]
    txt_path = participant_markdown_path(task_id, pdf_url)
    if not txt_path.exists():
        raise FileNotFoundError(f"{task_id}: missing parsed participant {txt_path} — run parse_fulltext.py first")

    text = txt_path.read_text(encoding="utf-8")

    candidates, third_party, tira_refs = extract_links(text)
    if third_party:
        logger.info("%s: excluded %d third-party dependency link(s)", pdf_url, len(third_party))
    if not candidates and not tira_refs:
        logger.info("%s: no code links found", pdf_url)
        return {"pdf_url": pdf_url, "code_urls": [], "third_party_urls": third_party, "tira_refs": tira_refs}

    validated = []
    for c in candidates:
        status = validate_url(c["url"], logger)
        link = {"url": c["url"], "status": status, "evidence": c["evidence"]}
        if task is not None:
            readme = fetch_readme(c["url"]) if status == "200" else None
            probability = own_code_probability(link_features(c["url"], c["before"], c["after"], readme, task, participant))
            link["own_code_score"] = round(probability, 3)
            link["likely_own_code"] = probability >= OWN_CODE_THRESHOLD
        validated.append(link)
    # A link still ending in "-" or "_" that does not resolve is a truncated fragment.
    validated = [v for v in validated if v["status"] == "200" or not v["url"].endswith(("-", "_"))]
    return {"pdf_url": pdf_url, "code_urls": validated, "third_party_urls": third_party, "tira_refs": tira_refs}


def process_task(task: dict, logger: logging.Logger, *, refresh: bool = False) -> list[dict]:
    task_id = task["task_id"]
    out_path = CODE_DIR / f"{task_id}.json"
    if out_path.exists() and not refresh:
        logger.info("code cache hit: %s", out_path)
        return json.loads(out_path.read_text(encoding="utf-8"))

    # Check every distinct URL of the task concurrently first; process_participant then
    # reads the cached statuses.
    urls = set()
    for p in task["participants"]:
        path = participant_markdown_path(task_id, p["pdf_url"])
        if not path.exists():
            raise FileNotFoundError(f"{task_id}: missing parsed participant {path} — run parse_fulltext.py first")
        urls |= {c["url"] for c in extract_links(path.read_text(encoding="utf-8"))[0]}
    validate_all(urls, logger)
    fetch_readmes_all({u for u in urls if _STATUS_CACHE.get(u) == "200"})
    results = [process_participant(task_id, p, logger, task) for p in task["participants"]]

    CODE_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve participant code links for candidate tasks.")
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to process (default: high only).")
    parser.add_argument("--task-id", type=str, default=None, help="Process only this single task_id (for testing).")
    parser.add_argument("--reuse-statuses", type=str, default=None, metavar="OLD_CODE_DIR", help="Reuse 200/404 statuses from an earlier run's code directory.")
    parser.add_argument("--refresh", action="store_true", help="Re-extract links even when a task cache exists.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("find_code")
    logger.info("logging to %s", log_path)

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    if args.reuse_statuses:
        global CODE_DIR
        keep, CODE_DIR = CODE_DIR, Path(args.reuse_statuses)
        load_known_statuses()
        CODE_DIR = keep
    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.task_id is not None:
        tasks = [t for t in tasks if t["task_id"] == args.task_id]
    elif args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]

    total_participants = 0
    with_code = 0
    for task in tasks:
        results = process_task(task, logger, refresh=args.refresh)
        total_participants += len(results)
        with_code += sum(1 for r in results if r["code_urls"] or r["tira_refs"])
        logger.info("%s: %d/%d participants have a resolved link", task["task_id"], sum(1 for r in results if r["code_urls"] or r["tira_refs"]), len(results))

    logger.info("processed %d tasks, %d participant papers: %d have at least one resolved code/TIRA link", len(tasks), total_participants, with_code)


if __name__ == "__main__":
    main()
