"""Links to code, datasets, models (and TIRA) found in a paper's text.

Every document, overviews included, gets ``links``: a list of
``{"url", "kind": code|dataset|model|tira, "third_party", "in_references", "own_code_score"}``. Links are read
from the body (Markdown hrefs authoritative; links after the reference list are kept but flagged) and are not fetched.
Reuses the repository canonicalisation and third-party list from ``find_code``.
"""

from __future__ import annotations

import re
import json
from pathlib import Path

from src.find_code import (
    MARKDOWN_ESCAPE_RE,
    MARKDOWN_LINK_RE,
    TIRA_URL_RE,
    canonical_repo_url,
    clean_url,
    is_third_party,
    rejoin_fenced_urls,
)

LINK_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.[a-z0-9.\-]+|zenodo\.org/records?|huggingface\.co"
    r"|kaggle\.com/(?:datasets|models)|figshare\.com|osf\.io)/[^\s\])>\"'<`|{}\\]*",
    re.IGNORECASE,
)
DATASET_CONTEXT_RE = re.compile(r"data\s?set|corpus|corpora|\bdata\b|annotat", re.IGNORECASE)
# Reviewed artifact kinds are data, with paper/README evidence kept beside the decision.
ARTIFACT_KINDS = json.loads(
    (Path(__file__).resolve().parent.parent / "curation" / "artifact_kinds.json").read_text(encoding="utf-8")
)
# The parser writes headings as "## References".
REFERENCES_RE = re.compile(r"(?im)^[ \t]*#*[ \t]*(?:\d+\.?\s*)?(?:references|bibliography|works cited)[ \t]*$")


def references_start(text: str) -> int:
    """Offset of the reference list (last heading, past the first third), else len(text)."""
    matches = list(REFERENCES_RE.finditer(text))
    return matches[-1].start() if matches and matches[-1].start() >= len(text) * 0.3 else len(text)


def canonical_link(url: str) -> str | None:
    """One stable spelling per link, or None when it names no concrete resource."""
    url = clean_url(url)
    match = re.match(r"https?://(?:www\.)?(kaggle\.com|figshare\.com|osf\.io)/([^?#]*)", url, re.IGNORECASE)
    if match:
        host, segments = match.group(1).lower(), [s for s in match.group(2).split("/") if s]
        if host == "kaggle.com":
            segments = segments[:3]  # datasets|models / owner / name
            return f"https://www.kaggle.com/{'/'.join(segments)}" if len(segments) == 3 else None
        return f"https://{host}/{'/'.join(segments[:3])}" if segments else None
    return canonical_repo_url(url)


def kind_of(url: str, context: str) -> str:
    if url.lower() in ARTIFACT_KINDS:
        return ARTIFACT_KINDS[url.lower()]["kind"]
    if "huggingface.co/datasets/" in url or "kaggle.com/datasets/" in url or "figshare.com" in url or "osf.io" in url:
        return "dataset"
    if "huggingface.co/spaces/" in url:
        return "code"
    if "huggingface.co/" in url or "kaggle.com/models/" in url:
        return "model"
    if "zenodo.org" in url:
        return "dataset" if DATASET_CONTEXT_RE.search(context) else "code"
    return "code"


def document_links(text: str, own_code_scores: dict[str, float] | None = None) -> list[dict]:
    """Links of one document in order of first appearance."""
    # Nothing is dropped: teams often put their own repository after the reference list (last
    # page, footnote), so links there are kept and marked ``in_references`` instead.
    body = MARKDOWN_LINK_RE.sub(r" \1 ", text)
    body = MARKDOWN_ESCAPE_RE.sub(r"\1", body)
    body = rejoin_fenced_urls(body)
    ref_start = references_start(body)
    found: dict[str, dict] = {}
    for match in LINK_RE.finditer(body):
        url = canonical_link(match.group(0))
        # A name ending in - or _ is usually a line-wrapped fragment; keep it only when
        # find_code verified the repository exists (it is then in own_code_scores).
        if not url or url in found or (url.endswith(("-", "_")) and url not in (own_code_scores or {})):
            continue
        context = body[max(0, match.start() - 160):match.end() + 160]
        found[url] = {
            "url": url,
            "kind": kind_of(url, context),
            "third_party": is_third_party(url),
            "in_references": match.start() >= ref_start,
            "own_code_score": (own_code_scores or {}).get(url),
        }
    for tira in sorted({clean_url(u) for u in TIRA_URL_RE.findall(body)}):
        found.setdefault(tira, {"url": tira, "kind": "tira", "third_party": False, "in_references": False, "own_code_score": None})
    return list(found.values())
