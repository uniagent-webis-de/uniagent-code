"""Normalise author lists: one person per entry, no affiliations, no scraped junk.

Sources sometimes store a whole author line as one string ("A, B and C - University of X"),
append the affiliation to a name ("A, University of X"), or leak page markup. Names are kept
as printed; only the packaging is cleaned.
"""

import html
import re

AFFILIATION_RE = re.compile(
    r"univers|hochschule|institut|college|school|laborator|\blab\b|department|dept\b|faculty|centre|center|academy|"
    r"research|corporation|\bcorp\b|\binc\b|\bltd\b|\bgmbh\b|company|group|team\b|hospital|clinic|"
    r"\bnist\b|\bcnrs\b|\binria\b|\bibm\b|google|microsoft|baidu|alibaba|tencent|yahoo|amazon|"
    r"healthcare|technolog|ministry|defen[cs]e|national|association|foundation|\bsciences?\b",
    re.IGNORECASE,
)
JUNK_RE = re.compile(r"@|\{|\}|javascript|cloudflare|https?://|\\u|<|>", re.IGNORECASE)
SEPARATOR_RE = re.compile(r"\s*(?:,|;|\band\b|&|\s-\s|\s–\s)\s*", re.IGNORECASE)
NAME_TOKEN_RE = re.compile(r"^[^\W\d_][\w'’.\-ʼ]*$", re.UNICODE)


def looks_like_name(part: str) -> bool:
    tokens = part.split()
    if not 2 <= len(tokens) <= 6 or AFFILIATION_RE.search(part) or JUNK_RE.search(part):
        return False
    return all(NAME_TOKEN_RE.match(t) for t in tokens)


def clean_authors(authors) -> list[str]:
    """Return a clean list of person names (possibly empty)."""
    if isinstance(authors, str):
        authors = [authors]
    names: list[str] = []
    for entry in authors or []:
        entry = html.unescape(str(entry)).replace(" ", " ").strip()
        # "Name (University of X)Name2 (University of Y)": close each group, then drop it.
        entry = re.sub(r"\s*\([^)]*\)\s*", ", ", entry).strip(" ,") if "(" in entry else entry
        if not entry or JUNK_RE.search(entry):
            continue
        # A plain short entry that already is one name stays untouched.
        if not re.search(r",|;|\band\b|&|\s-\s", entry) and not AFFILIATION_RE.search(entry) and len(entry) >= 3:
            names.append(entry)
            continue
        parts = [p.strip(" .") for p in SEPARATOR_RE.split(entry) if p.strip(" .")]
        found = [p for p in parts if looks_like_name(p)]
        # "SATO, Takashi" style (surname, given name): keep the entry whole.
        if len(parts) == 2 and all(len(p.split()) == 1 for p in parts):
            names.append(entry)
        else:
            names.extend(found)
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]


PAGES_RE = re.compile(r"\s+pp?\.\s*\d+(?:\s*[-–]\s*\d+)?\s*$", re.IGNORECASE)


def clean_title(title: str, authors: list[str]) -> str:
    """Remove a trailing page range and the author list that some proceedings pages append to
    the title: cut at the first author's name when everything after it is only names."""
    title = PAGES_RE.sub("", title).strip()
    if authors:
        cut = title.find(authors[0], 12)
        if cut > 0:
            rest = re.sub(r"\band\b|[,;&.]", " ", title[cut:], flags=re.IGNORECASE)
            if all(re.match(r"^[^\W\d_][\w'’\-]*$", t) and (t[0].isupper() or len(t) <= 2) for t in rest.split()):
                title = title[:cut].strip(" ,;:-")
    return title
