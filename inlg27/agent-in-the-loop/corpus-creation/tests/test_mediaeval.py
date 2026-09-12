import logging
from pathlib import Path

from src.collect_mediaeval import (
    build_task_candidate,
    combine_umbrella_sections,
    parse_ceur_mediaeval,
    parse_legacy_ceur_mediaeval,
    parse_dblp_titles,
    parse_legacy_mediaeval_page,
    parse_tira_refs,
)


LOGGER = logging.getLogger("test_mediaeval")
FIXTURES = Path(__file__).parent / "fixtures"
EDITION = {
    "parent_venue": "MediaEval",
    "year": 2022,
    "collection_id": "mediaeval2022",
    "ceur_volume": "3583",
    "proceedings_url": "https://ceur-ws.org/Vol-3583/",
    "official_url": "https://multimediaeval.github.io/editions/2022/",
}


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ceur_mediaeval_parser_preserves_explicit_paper_roles():
    sections = parse_ceur_mediaeval(read_fixture("mediaeval_ceur.html"), "3583")
    assert [section["lab_name"] for section in sections] == [
        "Search and Recommendation", "Insight Quest", "Unlabeled Task"
    ]
    assert [paper["role"] for paper in sections[0]["papers"]] == [
        "overview", "working_notes", "working_notes"
    ]
    assert sections[0]["papers"][1]["authors"] == ["Alice Alpha", "Alex Author"]
    assert sections[1]["papers"][1]["role"] == "quest_for_insight"


def test_role_complete_task_is_high_confidence():
    section = parse_ceur_mediaeval(read_fixture("mediaeval_ceur.html"), "3583")[0]
    candidate = build_task_candidate(
        section,
        EDITION,
        section["papers"],
        set(),
        set(),
        [],
        LOGGER,
    )
    assert candidate["task_id"] == "mediaeval2022-search-and-recommendation"
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["screening"]["decision"] == "include"
    assert len(candidate["participants"]) == 2
    assert candidate["participants"][0]["paper_type"] == "working_notes"


def test_unlabeled_or_incomplete_task_is_review_only():
    section = parse_ceur_mediaeval(read_fixture("mediaeval_ceur.html"), "3583")[2]
    candidate = build_task_candidate(
        section,
        EDITION,
        section["papers"],
        set(),
        set(),
        [],
        LOGGER,
    )
    assert candidate["provenance"]["confidence"] == "medium"
    assert candidate["screening"]["decision"] == "review"
    assert candidate["participants"] == []
    assert "paper(s) have no explicit participant role" in " ".join(
        candidate["provenance"]["confidence_reasons"]
    )


def test_legacy_parser_is_conservative_and_resolves_relative_pdfs():
    sections = parse_legacy_mediaeval_page(
        read_fixture("mediaeval_legacy.html"),
        "http://multimediaeval.org/mediaeval2010/photo/",
    )
    assert sections[0]["lab_name"] == "Historical MediaEval Task 2010"
    assert sections[0]["papers"][0]["pdf_url"] == (
        "http://multimediaeval.org/mediaeval2010/photo/overview.pdf"
    )
    assert sections[0]["papers"][0]["role"] == "overview"


def test_early_ceur_layout_fallback_uses_ordinary_task_headings():
    html = """
    <h1>Table of Contents</h1>
    <h2>Early Task</h2>
    <h4>Overview paper:</h4>
    <ul><li><a href="o.pdf"><span class="CEURTITLE">Early overview</span></a></li></ul>
    <h4>Working notes papers:</h4>
    <ul>
      <li><a href="a.pdf"><span class="CEURTITLE">Alpha system</span></a></li>
      <li><a href="b.pdf"><span class="CEURTITLE">Beta system</span></a></li>
    </ul>
    """
    sections = parse_legacy_ceur_mediaeval(html, "807")
    assert [section["lab_name"] for section in sections] == ["Early Task"]
    assert [paper["role"] for paper in sections[0]["papers"]] == [
        "overview", "working_notes", "working_notes"
    ]


def test_dblp_and_tira_are_supplemental_only():
    assert parse_dblp_titles(
        '<html><title>Making sure you are not a bot</title></html>'
    ) == set()
    raw = '<a href="/task-overview/mediaeval-search-2022">Search task 2022</a>'
    assert parse_tira_refs(raw, 2022, "Search and Recommendation") == [
        "https://www.tira.io/task-overview/mediaeval-search-2022"
    ]


def test_shared_multi_task_overview_is_combined_into_one_umbrella_candidate():
    overview = {
        "title": "Overview of MediaEval 2011 Rich Speech Retrieval Task and Genre Tagging Task",
        "role": "overview",
        "pdf_url": "https://ceur-ws.org/Vol-807/overview.pdf",
    }
    sections = combine_umbrella_sections([
        {"lab_name": "Genre Tagging Task", "papers": [overview, {"role": "working_notes", "pdf_url": "a.pdf", "title": "A"}]},
        {"lab_name": "Rich Speech Retrieval Task", "papers": [overview, {"role": "working_notes", "pdf_url": "b.pdf", "title": "B"}]},
    ])
    assert len(sections) == 1
    assert sections[0]["is_umbrella"] is True
    assert sections[0]["lab_name"] == "Genre Tagging Task + Rich Speech Retrieval Task"
    assert [paper["pdf_url"] for paper in sections[0]["papers"]] == [
        "https://ceur-ws.org/Vol-807/overview.pdf", "a.pdf", "b.pdf"
    ]
