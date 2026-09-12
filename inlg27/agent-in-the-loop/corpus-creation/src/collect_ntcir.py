#!/usr/bin/env python
"""Collect high-precision NTCIR task candidates from official NII ToCs.

NTCIR proceedings have evolved from clean HTML task sections to older flat
pages.  The parser keeps the official section hierarchy, ignores general
conference material, and only emits a high-confidence candidate when one
official overview and at least two distinct participant PDFs occur in the same
explicit task section.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidate_schema import slugify, write_jsonl
from src.corpus_paths import CANDIDATES_DIR, SCREENING_DIR
from src.fetch_ntcir import discover_toc_url
from src.ntcir_config import selected_editions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ntcir"
LOGS_DIR = PROJECT_ROOT / "logs"

PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
OVERVIEW_RE = re.compile(r"\boverview\b|task\s+(?:final\s+)?report", re.IGNORECASE)
OVERVIEW_FILE_RE = re.compile(r"(?:^|[-_/])ov(?:[-_.]|$)|overview", re.IGNORECASE)
SECTION_MARKER_RE = re.compile(r"^\s*-{2,}\s*(?P<label>.+?)\s*-{2,}\s*$")
NUMBERED_TASK_RE = re.compile(r"^\s*(?P<major>\d+)\.\s*(?P<label>.+?\bTasks?\b.*)$", re.IGNORECASE)
NUMBERED_SUBSECTION_RE = re.compile(r"^\s*(?P<major>\d+)\.(?P<minor>\d+)\s+(?P<label>.+)$", re.IGNORECASE)
NUMBERED_TOP_RE = re.compile(r"^\s*(?P<major>\d+)\.\s+(?P<label>.+)$", re.IGNORECASE)
EXCLUDED_SECTION_RE = re.compile(
    r"^(?:preface|overview|keynote|keynote speech|panel|organization|publication information|"
    r"author index|evaluation results?|program|welcome|wrap[- ]?up|advisory report|"
    r"table of contents|tutorials?|invited talks?|invited speech|open submission|"
    r"supplemental material|without oral presentation|research papers|"
    r"proposal for the next ntcir workshop)$|"
    r"\b(?:keynote|panel|preface|author index|publication information|organization|"
    r"table of contents|ntcir workshop \d+|proceedings of the \d+(?:st|nd|rd|th) ntcir conference|"
    r"tutorial|invited talk|invited speech|open submission|supplemental material|"
    r"without oral presentation|research papers|evaluation results?|system description form)\b",
    re.IGNORECASE,
)
EXCLUDED_PAPER_RE = re.compile(
    r"\b(?:poster|slides?|abstract|keynote|panel|preface|invited talk|"
    r"publication information|author index|organization|evaluation results?|advisory report)\b",
    re.IGNORECASE,
)
GENERAL_OVERVIEW_RE = re.compile(
    r"^ntcir\s*\d+[- ]*overview(?:\.pdf)?$|overview of the \w+ ntcir workshop$",
    re.IGNORECASE,
)

# The official NTCIR-12 IMine-2 ToC links this paper as ``SongX`` although
# NII serves the corresponding PDF as ``SongM``.  Keep this correction narrow
# and explicit so a broken official href does not permanently demote an
# otherwise structurally high-confidence task.
NTCIR_PDF_URL_ALIASES = {
    "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings12/pdf/ntcir/IMINE/08-NTCIR12-IMINE-SongX.pdf":
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings12/pdf/ntcir/IMINE/08-NTCIR12-IMINE-SongM.pdf",
}


def setup_logging() -> Path:
    """Create a readable, write-mode stage log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"collect_ntcir_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def clean_text(value: str) -> str:
    """Collapse HTML whitespace without changing title punctuation."""
    return re.sub(r"\s+", " ", value).strip()


def section_name(value: str) -> str:
    """Normalize an official section heading such as ``[FairWeb-2]``."""
    value = clean_text(value)
    value = re.sub(r"\(?return\s+to\s+top\)?", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d+(?:\.\d+)*\s+", "", value)
    value = re.sub(r"\bretieval\b", "retrieval", value, flags=re.IGNORECASE)
    value = re.sub(r"\bsesseion\b", "session", value, flags=re.IGNORECASE)
    value = re.sub(r"^\[|\]$", "", value).strip()
    return clean_text(value)


def section_key(value: str) -> str:
    """Normalize section labels shared by overview and research-paper parts."""
    value = re.sub(r"\([^)]*\)", "", section_name(value))
    value = re.sub(r"\bretieval\b", "retrieval", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _pdf_anchors(node) -> list:
    if node.name == "a" and PDF_RE.search(node.get("href", "")):
        return [node]
    return [anchor for anchor in node.find_all("a", href=True) if PDF_RE.search(anchor.get("href", ""))]


def _title_from_entry(node) -> str:
    title_node = node.find(class_=re.compile(r"paper[_-]?title", re.IGNORECASE))
    if (
        title_node is None
        and node.name == "a"
        and re.search(r"(?:^|\s)title(?:\s|$)", " ".join(node.get("class", [])), re.IGNORECASE)
    ):
        title_node = node
    if title_node is None and node.name == "a":
        title_node = node.find_previous("a", class_=re.compile(r"^title$", re.IGNORECASE))
    if title_node is None and node.name == "a":
        parts: list[str] = []
        for previous in node.previous_siblings:
            if getattr(previous, "name", None) == "br":
                break
            text = previous.get_text(" ", strip=True) if hasattr(previous, "get_text") else str(previous)
            if text.strip():
                parts.insert(0, text)
        if parts:
            title_node = " ".join(parts)
    if title_node is None:
        title_node = node.find("b")
    if isinstance(title_node, str):
        title = title_node
    elif title_node is None:
        title = node.get_text(" ", strip=True)
    else:
        title = title_node.get_text(" ", strip=True)
    quoted = re.match(r"^[\"“](.+?)[\"”]", title)
    if quoted:
        title = quoted.group(1)
    title = re.sub(r"\[(?:pdf|poster|slides?|abstract)[^\]]*\]", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(?:pdf|poster|slides?)\b\s*$", "", title, flags=re.IGNORECASE)
    return clean_text(title.strip(" \"'“”"))


def _authors_from_entry(node) -> list[str]:
    author_node = node.find(class_=re.compile(r"paper[_-]?authors", re.IGNORECASE))
    if author_node is None and node.name == "a":
        author_node = node.find_next("span", class_=re.compile(r"^author$", re.IGNORECASE))
    if author_node is None:
        return []
    text = clean_text(author_node.get_text(" ", strip=True))
    return [text] if text else []


def repair_pdf_url(source_url: str) -> str:
    """Apply only verified, source-specific repairs to official PDF hrefs."""
    return NTCIR_PDF_URL_ALIASES.get(source_url, source_url)


def parse_entry(node, base_url: str) -> dict | None:
    """Parse an official ToC block containing one or more source links."""
    anchors = _pdf_anchors(node)
    if not anchors:
        return None
    anchor = anchors[0]
    original_url = urljoin(base_url, anchor.get("href", "").strip())
    source_url = repair_pdf_url(original_url)
    title = _title_from_entry(node)
    if not title:
        return None
    path_name = Path(urlparse(source_url).path).name
    parsed = {
        "source_id": path_name,
        "source_url": source_url,
        "pdf_url": source_url,
        "source_format": "pdf",
        "title": title,
        "authors": _authors_from_entry(node),
        "team_name": None,
        "is_overview": bool(OVERVIEW_RE.search(title) or OVERVIEW_FILE_RE.search(path_name)),
    }
    if original_url != source_url:
        parsed["source_url_original"] = original_url
    return parsed


def _section_headers(soup) -> list[tuple[object, str]]:
    """Find named HTML headings and the named centered paragraphs used by NTCIR-4."""
    headers: list[tuple[object, str]] = []
    seen: set[int] = set()
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        anchor = heading.find("a", attrs={"name": True})
        label_text = clean_text(heading.get_text(" ", strip=True))
        numbered_task = bool(
            re.match(r"^\s*\d+(?:\.\d+)*\s+", label_text)
            and re.search(r"\b(?:task|retrieval|question|summarization|clir|web)\b", label_text, re.IGNORECASE)
        )
        if anchor is None and not heading.get("id") and not numbered_task:
            continue
        label = section_name(label_text)
        if not label or "table of contents" in label.casefold() or label.casefold() in {"top", "return to top"}:
            continue
        if label and id(heading) not in seen:
            headers.append((heading, label))
            seen.add(id(heading))
    for paragraph in soup.find_all("p"):
        if paragraph.find("a", attrs={"name": True}) is None:
            continue
        if paragraph.find("a", href=PDF_RE) is not None:
            continue
        if str(paragraph.get("align", "")).casefold() != "center":
            continue
        label = section_name(paragraph.get_text(" ", strip=True))
        if label and id(paragraph) not in seen:
            headers.append((paragraph, label))
            seen.add(id(paragraph))
    for anchor in soup.find_all("a", attrs={"name": True}):
        if anchor.find_parent("li") is not None or anchor.find_parent("dt") is not None:
            continue
        logo = anchor.find_parent(class_=re.compile(r"\blogo\b", re.IGNORECASE))
        if logo is None:
            continue
        label = section_name(anchor.get_text(" ", strip=True))
        if label and id(logo) not in seen:
            headers.append((logo, label))
            seen.add(id(logo))
    positions = {id(node): index for index, node in enumerate(soup.find_all(True))}
    headers.sort(key=lambda item: positions.get(id(item[0]), 0))
    return headers


def _entry_containers(soup, start: int, end: int) -> list[object]:
    """Return one container for each PDF link in a section range."""
    elements = soup.find_all(True)
    containers: list[object] = []
    seen: set[tuple[int, str]] = set()
    for index, element in enumerate(elements):
        if index < start or index >= end or element.name != "a" or not PDF_RE.search(element.get("href", "")):
            continue
        container = element.find_parent("li") or element.find_parent("dt") or element.find_parent("p")
        if container is None:
            # Some historical ToCs leave the title, PDF link, and author span
            # as direct siblings of the body. ``parse_entry`` resolves the
            # preceding class=title anchor for this representation.
            container = element
        key = (id(container), urljoin("", element.get("href", "")))
        if key not in seen:
            containers.append(container)
            seen.add(key)
    return containers


def parse_sectioned_page(raw_html: str, base_url: str) -> list[dict]:
    """Parse NTCIR pages with named h3/p task sections."""
    soup = BeautifulSoup(raw_html, "lxml")
    headers = _section_headers(soup)
    elements = soup.find_all(True)
    positions = {id(node): index for index, node in enumerate(elements)}
    sections: list[dict] = []
    for index, (header, label) in enumerate(headers):
        start = positions[id(header)]
        end = positions[id(headers[index + 1][0])] if index + 1 < len(headers) else len(elements)
        papers: list[dict] = []
        seen_urls: set[str] = set()
        for container in _entry_containers(soup, start, end):
            parsed = parse_entry(container, base_url)
            if parsed is None or parsed["source_url"] in seen_urls:
                continue
            papers.append(parsed)
            seen_urls.add(parsed["source_url"])
        sections.append({"task_name": label, "papers": papers, "explicit_section": True})
    return deduplicate_sections(sections)


def _flat_blocks(soup) -> list[tuple[int, str, object | None]]:
    """Create ordered marker/text/PDF events from the early flat NTCIR page."""
    elements = soup.find_all(True)
    events: list[tuple[int, str, object | None]] = []
    seen_text: set[tuple[str, str]] = set()
    seen_pdf_hrefs: set[str] = set()
    for index, element in enumerate(elements):
        if element.name == "a" and PDF_RE.search(element.get("href", "")):
            href = element.get("href", "").strip()
            if href in seen_pdf_hrefs:
                continue
            seen_pdf_hrefs.add(href)
            container = element.find_parent("li") or element.find_parent("dt") or element.find_parent("p")
            if container is not None and len(_pdf_anchors(container)) > 1:
                container = element
            if container is None:
                container = element
            events.append((index, "pdf", container))
            continue
        if element.name not in {"font", "p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            continue
        if element.find("a", href=PDF_RE) is not None:
            continue
        text = clean_text(element.get_text(" ", strip=True))
        marker = SECTION_MARKER_RE.match(text)
        numbered = NUMBERED_TASK_RE.match(text)
        subsection = NUMBERED_SUBSECTION_RE.match(text)
        top_level = NUMBERED_TOP_RE.match(text)
        if marker:
            key = ("marker", marker.group("label"))
            if key not in seen_text:
                events.append((index, "marker:" + section_name(marker.group("label")), None))
                seen_text.add(key)
        elif subsection:
            key = ("subsection", text)
            if key not in seen_text:
                events.append((
                    index,
                    f"subsection:{subsection.group('major')}:{section_name(subsection.group('label'))}",
                    None,
                ))
                seen_text.add(key)
        elif numbered:
            key = ("task", numbered.group("label"))
            if key not in seen_text:
                events.append((
                    index,
                    f"task:{numbered.group('major')}:{section_name(numbered.group('label'))}",
                    None,
                ))
                seen_text.add(key)
        elif top_level:
            key = ("top", text)
            if key not in seen_text:
                events.append((
                    index,
                    f"top:{top_level.group('major')}:{section_name(top_level.group('label'))}",
                    None,
                ))
                seen_text.add(key)
    events.sort(key=lambda item: item[0])
    return events


def parse_flat_page(raw_html: str, base_url: str) -> list[dict]:
    """Parse early proceedings where task markers and paper links are flat text."""
    soup = BeautifulSoup(raw_html, "lxml")
    sections: list[dict] = []
    by_name: dict[str, dict] = {}
    current: dict | None = None
    overview_context = False
    overview_seen = False
    for _, event, node in _flat_blocks(soup):
        if event.startswith(("task:", "marker:", "subsection:", "top:")):
            parts = event.split(":", 2)
            event_major = parts[1] if event.startswith(("task:", "subsection:", "top:")) else None
            label = parts[2] if event_major is not None else parts[1]
            if event.startswith(("task:", "top:")):
                current = None
                overview_context = False
                overview_seen = False
            elif (
                event.startswith("subsection:")
                and current is not None
                and current.get("broad_task")
                and current.get("task_major") == event_major
            ):
                # Early NTCIR-1 keeps one task's overview and research
                # sections under the same numbered task heading.
                overview_context = label.casefold().startswith("overview")
                overview_seen = False
                continue
            else:
                overview_context = event_major == "4"
                overview_seen = False
            if event.startswith("task:") and current is not None and current["task_name"] == label:
                continue
            current = by_name.get(label)
            if current is None:
                current = {
                    "task_name": label,
                    "papers": [],
                    "explicit_section": True,
                    "overview_context": overview_context,
                    "task_major": event_major,
                    "broad_task": event.startswith("task:"),
                }
                by_name[label] = current
                sections.append(current)
            continue
        if event == "pdf" and node is not None:
            parsed = parse_entry(node, base_url)
            if parsed is None:
                continue
            if current is None:
                current = {"task_name": "Unresolved NTCIR section", "papers": [], "explicit_section": False}
                sections.append(current)
            if overview_context and not overview_seen and not _excluded_paper(parsed):
                parsed["is_overview"] = True
                overview_seen = True
            if parsed["source_url"] not in {paper["source_url"] for paper in current["papers"]}:
                current["papers"].append(parsed)
    return deduplicate_sections(sections)


def parse_toc_page(raw_html: str, base_url: str) -> list[dict]:
    """Parse an official NTCIR ToC using the appropriate historical layout."""
    sections = parse_sectioned_page(raw_html, base_url)
    if sections and any(section["papers"] for section in sections):
        return sections
    return parse_flat_page(raw_html, base_url)


def deduplicate_sections(sections: list[dict]) -> list[dict]:
    """Merge overview/research sections and collapse duplicate navigation entries."""
    unique: dict[str, dict] = {}
    order: list[str] = []
    for section in sections:
        key = section_key(section["task_name"])
        previous = unique.get(key)
        if previous is None:
            unique[key] = {**section, "papers": list(section["papers"])}
            order.append(key)
        else:
            seen_urls = {paper["source_url"] for paper in previous["papers"]}
            previous["papers"].extend(
                paper for paper in section["papers"] if paper["source_url"] not in seen_urls
            )
            previous["explicit_section"] = previous.get("explicit_section", False) or section.get(
                "explicit_section", False
            )
            previous["overview_context"] = previous.get("overview_context", False) or section.get(
                "overview_context", False
            )
    return [unique[key] for key in order]


def normalize_title(title: str) -> str:
    """Normalize titles for supplemental DBLP matching."""
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def parse_dblp_titles(raw_html: str) -> set[str]:
    """Extract DBLP titles, returning an empty set for bot/challenge pages."""
    soup = BeautifulSoup(raw_html, "lxml")
    titles: set[str] = set()
    for entry in soup.select("li.entry.inproceedings"):
        title = entry.find("span", class_="title")
        if title is not None:
            titles.add(normalize_title(title.get_text(" ", strip=True).rstrip(".")))
    return titles


def parse_tira_refs(raw_html: str, edition: int, task_name: str) -> list[str]:
    """Find supplemental TIRA task links mentioning this NTCIR task."""
    soup = BeautifulSoup(raw_html, "lxml")
    tokens = set(normalize_title(task_name).split()) - {"task", "tasks"}
    refs: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = normalize_title(anchor.get_text(" ", strip=True) + " " + href)
        if "task overview" not in text and "task-overview" not in href.casefold():
            continue
        if "ntcir" not in text and "ntcir" not in href.casefold():
            continue
        if str(edition) not in text and str(edition) not in href:
            continue
        if tokens and not tokens.intersection(text.split()):
            continue
        refs.append(urljoin("https://www.tira.io", href))
    return sorted(set(refs))


def _excluded_paper(paper: dict) -> bool:
    return bool(
        EXCLUDED_PAPER_RE.search(paper["title"])
        or EXCLUDED_PAPER_RE.search(paper["source_id"])
        or re.match(r"^evaluation\s+of\b", paper["title"], re.IGNORECASE)
    )


def paper_record(paper: dict, task_name: str, collection_id: str, tira_refs: list[str]) -> dict:
    """Convert a parsed official entry to the common corpus record shape."""
    record = {
        "title": paper["title"],
        "authors": paper["authors"],
        "pdf_url": paper["pdf_url"],
        "team_name": paper["team_name"],
        "code_urls": [],
        "tira_refs": tira_refs,
        "source_id": paper["source_id"],
        "paper_url": paper["source_url"],
        "source_format": paper["source_format"],
        "source_collection_id": collection_id,
        "task_name": task_name,
    }
    if paper.get("source_url_original"):
        record["source_url_original"] = paper["source_url_original"]
    return record


def build_task_candidate(
    section: dict,
    edition: dict,
    duplicated_participant_urls: set[str],
    dblp_titles: set[str],
    tira_refs: list[str],
    logger: logging.Logger,
    toc_url: str | None = None,
) -> dict | None:
    """Build one candidate and demote structural ambiguity to review."""
    task_name = section["task_name"]
    papers = [
        paper for paper in section["papers"]
        if not _excluded_paper(paper) and not GENERAL_OVERVIEW_RE.search(paper["source_id"])
    ]
    if not papers or EXCLUDED_SECTION_RE.search(task_name):
        return None
    overviews = [paper for paper in papers if paper["is_overview"]]
    participants = [paper for paper in papers if paper not in overviews]
    participants = [paper for paper in participants if paper["source_url"] not in duplicated_participant_urls]
    excluded_shared = len([paper for paper in papers if paper not in overviews]) - len(participants)
    reasons: list[str] = []
    if len(overviews) != 1:
        reasons.append(f"expected exactly one official overview, found {len(overviews)}")
    if not overviews:
        logger.warning("NTCIR-%s %s: no official overview marker", edition["edition"], task_name)
        return {
            "record_type": "unresolved_ntcir_task",
            "venue": task_name,
            "parent_venue": "NTCIR",
            "year": edition["year"],
            "edition": edition["edition"],
            "task_name": task_name,
            "decision": "review",
            "reason": "official task section has no recognizable overview paper",
            "papers": papers,
            "source": {**edition, "toc_url": toc_url},
        }
    overview = overviews[0]
    if len(participants) < 2:
        reasons.append(f"found only {len(participants)} unambiguous participant papers")
    if overview["pdf_url"] is None or any(paper["pdf_url"] is None for paper in participants):
        reasons.append("all overview and participant entries must have official PDF links")
    if excluded_shared:
        reasons.append(f"excluded {excluded_shared} participant paper(s) listed under multiple task sections")
    participant_urls = [paper["pdf_url"] for paper in participants if paper["pdf_url"]]
    if len(participant_urls) != len(set(participant_urls)):
        reasons.append("duplicate participant PDF URL")

    confidence = "high" if not reasons else "medium"
    decision = "include" if confidence == "high" else "review"
    task_id = f"ntcir{edition['edition']}-{slugify(task_name)}"
    source = {
        "provider": "nii_ntcir",
        "collection_id": edition["collection_id"],
        "proceedings_url": edition["proceedings_url"],
        "toc_url": toc_url,
        "dblp_url": "https://dblp.org/db/conf/ntcir/index.html",
        "tira_refs": tira_refs,
    }
    # A singular task/track label is task-specific.  Only an explicitly plural
    # task hierarchy is marked umbrella; this mirrors the common corpus meaning
    # that one overview covers several sub-tasks.
    is_umbrella = bool(re.search(r"\b(?:tasks|tracks)\b", task_name, re.IGNORECASE))
    candidate = {
        "task_id": task_id,
        "venue": task_name,
        "parent_venue": "NTCIR",
        "year": edition["year"],
        "edition": edition["edition"],
        "task_name": task_name,
        "ceur_volume": None,
        "source": source,
        "overview": {
            **paper_record(overview, task_name, edition["collection_id"], tira_refs),
            "is_umbrella": is_umbrella,
        },
        "participants": [
            paper_record(paper, task_name, edition["collection_id"], tira_refs)
            for paper in participants
        ],
        "counts": {
            "notebook_papers": len(participants),
            "teams_claimed_in_overview": None,
            "runs_claimed_in_overview": None,
            "coverage_ratio": None,
        },
        "provenance": {
            "task_assignment_method": "official_nii_task_section",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "extracted_at": datetime.now().date().isoformat(),
            "dblp_overview_match": bool(dblp_titles and normalize_title(overview["title"]) in dblp_titles),
            "tira_task_matches": tira_refs,
        },
        "screening": {
            "decision": decision,
            "checks": {
                "one_overview": len(overviews) == 1,
                "official_task_section": bool(section.get("explicit_section")),
                "minimum_participants": len(participants) >= 2,
                "official_pdf_links": overview["pdf_url"] is not None and all(
                    paper["pdf_url"] is not None for paper in participants
                ),
                "unique_pdf_urls": len(participant_urls) == len(set(participant_urls)),
                "no_multi_task_participants": excluded_shared == 0,
            },
        },
    }
    logger.info(
        "%s: %s (%d participant papers; confidence=%s)",
        task_id, decision, len(participants), confidence,
    )
    return candidate


def _load_edition_metadata(edition: dict) -> dict:
    path = RAW_DIR / "editions" / edition["collection_id"] / "metadata.json"
    if not path.exists():
        return edition
    try:
        import json

        return {**edition, **json.loads(path.read_text(encoding="utf-8"))}
    except (ValueError, OSError):
        return edition


def collect_edition(edition: dict, logger: logging.Logger) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect one cached NTCIR edition."""
    edition = _load_edition_metadata(edition)
    edition_dir = RAW_DIR / "editions" / edition["collection_id"]
    index_path = edition_dir / "index.html"
    toc_path = edition_dir / "toc.html"
    if toc_path.exists():
        source_path = toc_path
    elif index_path.exists():
        source_path = index_path
    else:
        raise FileNotFoundError(f"missing cached NTCIR proceedings: {toc_path}")
    raw_html = source_path.read_text(encoding="utf-8")
    toc_url = edition.get("toc_url")
    if not toc_url and index_path.exists():
        toc_url = discover_toc_url(
            index_path.read_text(encoding="utf-8"), edition["proceedings_url"], edition["edition"]
        )
    if not toc_url:
        toc_url = edition["proceedings_url"]
    sections = parse_toc_page(raw_html, toc_url)
    if not sections:
        return [], [{
            "record_type": "unresolved_ntcir_edition",
            "venue": "NTCIR",
            "parent_venue": "NTCIR",
            "year": edition["year"],
            "edition": edition["edition"],
            "decision": "review",
            "reason": "no task sections could be parsed from the cached NII page",
            "source": {**edition, "toc_url": toc_url},
        }], []

    dblp_path = RAW_DIR / "dblp.html"
    dblp_titles = parse_dblp_titles(dblp_path.read_text(encoding="utf-8")) if dblp_path.exists() else set()
    tira_path = RAW_DIR / "tira-tasks.html"
    tira_html = tira_path.read_text(encoding="utf-8") if tira_path.exists() else ""
    occurrences: defaultdict[str, set[str]] = defaultdict(set)
    for section in sections:
        for paper in section["papers"]:
            if not paper["is_overview"] and not _excluded_paper(paper):
                occurrences[paper["source_url"]].add(section["task_name"])
    duplicated = {url for url, names in occurrences.items() if len(names) > 1}

    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    for section in sections:
        tira_refs = parse_tira_refs(tira_html, edition["edition"], section["task_name"])
        record = build_task_candidate(section, edition, duplicated, dblp_titles, tira_refs, logger, toc_url)
        if record is None:
            if section["papers"] and EXCLUDED_SECTION_RE.search(section["task_name"]):
                excluded.append({
                    "record_type": "excluded_ntcir_section",
                    "venue": section["task_name"],
                    "year": edition["year"],
                    "edition": edition["edition"],
                    "reason": "general proceedings material, not a shared task",
                })
            continue
        if "task_id" not in record:
            review.append(record)
        else:
            candidates.append(record)
            if record["provenance"]["confidence"] != "high":
                review.append(record)
    logger.info(
        "NTCIR-%s: parsed %d sections, %d candidates, %d review records, %d excluded sections",
        edition["edition"], len(sections), len(candidates), len(review), len(excluded),
    )
    return candidates, review, excluded


def write_screening_report(candidates: list[dict], review: list[dict], excluded: list[dict], path: Path) -> None:
    """Write a compact generated NTCIR screening report."""
    high = [candidate for candidate in candidates if candidate["provenance"]["confidence"] == "high"]
    lines = [
        "# NTCIR screening report",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        f"Candidate task groups: {len(candidates)}",
        f"High-confidence tasks: {len(high)}",
        f"Tasks/records needing review: {len(review)}",
        f"Excluded records: {len(excluded)}",
        "",
        "## High-confidence tasks",
        "",
    ]
    lines.extend(
        f"- `{candidate['task_id']}` — {len(candidate['participants'])} participants — "
        f"overview: {candidate['overview']['paper_url']}"
        for candidate in high
    )
    lines += ["", "## Review records", ""]
    for record in review:
        if "task_id" in record:
            reasons = "; ".join(record["provenance"].get("confidence_reasons", [])) or "unspecified"
            lines.append(f"- `{record['task_id']}` — {reasons}")
        else:
            lines.append(
                f"- NTCIR-{record.get('edition')} {record.get('task_name', 'edition')} — "
                f"{record.get('reason', 'review')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_all(edition: int | None, logger: logging.Logger) -> bool:
    """Process selected cached editions and write NTCIR source outputs."""
    editions = selected_editions(edition)
    if not editions:
        logger.error("no configured NTCIR edition %s", edition)
        return False
    candidates: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    try:
        for item in editions:
            item_candidates, item_review, item_excluded = collect_edition(item, logger)
            candidates.extend(item_candidates)
            review.extend(item_review)
            excluded.extend(item_excluded)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("NTCIR collection failed: %s", exc)
        return False

    candidates.sort(key=lambda candidate: candidate["task_id"])
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(candidates, CANDIDATES_DIR / "ntcir.jsonl")
    write_jsonl(candidates, SCREENING_DIR / "ntcir.jsonl")
    write_jsonl(review, SCREENING_DIR / "ntcir_review.jsonl")
    write_jsonl(excluded, SCREENING_DIR / "ntcir_excluded.jsonl")
    write_screening_report(candidates, review, excluded, SCREENING_DIR / "ntcir_report.md")
    logger.info(
        "wrote %d NTCIR candidates (%d high, %d review) to %s",
        len(candidates), sum(1 for candidate in candidates if candidate["provenance"]["confidence"] == "high"),
        len(review), CANDIDATES_DIR / "ntcir.jsonl",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and screen NTCIR task candidates from cached NII proceedings.")
    parser.add_argument("--edition", type=int, help="Collect only one configured NTCIR edition number.")
    args = parser.parse_args()
    log_path = setup_logging()
    logger = logging.getLogger("collect_ntcir")
    logger.info("logging to %s", log_path)
    raise SystemExit(0 if collect_all(args.edition, logger) else 1)


if __name__ == "__main__":
    main()
