import logging
from pathlib import Path

from src.collect_fire import (
    assign_by_title,
    build_task_candidate,
    clean_task_name,
    parse_dblp_titles,
    parse_legacy_fire_page,
    parse_tira_refs,
    prepare_papers,
    tokenize,
)
from src.parse_sections import parse_ceur_volume


LOGGER = logging.getLogger("test_fire")
FIXTURES = Path(__file__).parent / "fixtures"
EDITION = {
    "parent_venue": "FIRE",
    "edition": 17,
    "year": 2025,
    "collection_id": "fire2025",
    "ceur_volume": "4173",
    "proceedings_url": "https://ceur-ws.org/Vol-4173/",
    "official_url": "https://fire.irsi.org.in/fire/2025/home",
    "dblp_url": "https://dblp.org/db/conf/fire/fire2025.html",
}


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ceur_fire_sections_preserve_official_track_boundaries():
    sections = parse_ceur_volume(read_fixture("fire_ceur.html"), "4173")
    assert [section["lab_name"] for section in sections] == [
        "Demo Task (DEMO)", "Multi Task Lab (MTL)", "Preface"
    ]
    papers = prepare_papers(sections[0])
    assert len(papers) == 3
    assert papers[0]["is_overview"] is True
    assert papers[0]["authors"] == ["Organizer One"]


def test_single_overview_candidate_is_high_confidence():
    section = parse_ceur_volume(read_fixture("fire_ceur.html"), "4173")[0]
    papers = prepare_papers(section)
    overviews = [paper for paper in papers if paper["is_overview"]]
    participants = [paper for paper in papers if not paper["is_overview"]]
    candidate = build_task_candidate(
        {"lab_name": section["lab_name"]},
        EDITION,
        overviews[0],
        participants,
        overviews,
        set(),
        [],
        set(),
        [],
        LOGGER,
    )
    assert candidate["task_id"] == "fire2025-demo-task-demo"
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["screening"]["decision"] == "include"
    assert len(candidate["participants"]) == 2


def test_multi_overview_title_assignment_is_review_only():
    section = parse_ceur_volume(read_fixture("fire_ceur.html"), "4173")[1]
    papers = prepare_papers(section)
    overviews = [paper for paper in papers if paper["is_overview"]]
    assignments, unresolved = assign_by_title(papers, overviews, LOGGER, section["lab_name"])
    assert unresolved == []
    assert [paper["title"] for paper in assignments[id(overviews[0])]] == [
        "Team Widget: Widget retrieval approach"
    ]
    candidate = build_task_candidate(
        {"lab_name": section["lab_name"]},
        EDITION,
        overviews[0],
        assignments[id(overviews[0])],
        overviews,
        set(),
        unresolved,
        set(),
        [],
        LOGGER,
    )
    assert candidate["provenance"]["confidence"] == "medium"
    assert "title-based split" in " ".join(candidate["provenance"]["confidence_reasons"])


def test_legacy_page_parser_is_conservative_and_structured():
    sections = parse_legacy_fire_page(read_fixture("fire_legacy.html"), "https://example.org/fire/2014/")
    assert [section["lab_name"] for section in sections] == ["Historical Task"]
    assert [paper["title"] for paper in sections[0]["papers"]] == [
        "Overview of the Historical Task", "Alpha system", "Beta system"
    ]
    assert sections[0]["papers"][0]["pdf_url"] == "https://example.org/fire/2014/overview.pdf"


def test_supplemental_dblp_and_tira_sources_never_create_records():
    assert parse_dblp_titles("<html><title>Making sure you are not a bot</title></html>") == set()
    raw = '<a href="/task-overview/fire-demo-2025">FIRE Demo Task Overview 2025</a>'
    assert parse_tira_refs(raw, 2025, "Demo Task") == [
        "https://www.tira.io/task-overview/fire-demo-2025"
    ]


def test_title_normalization_removes_generic_words():
    assert tokenize("Overview of the Widget Retrieval Task at FIRE 2025") == {"widget"}
    assert clean_task_name("Overview of the Widget Task at FIRE 2025", "Fallback") == "Widget Task"
