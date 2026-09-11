import logging
from pathlib import Path

from src.collect_trec import (
    attach_overview_papers,
    build_task_candidate,
    parse_dblp_titles,
    parse_overview_index,
    parse_track_page,
    parse_tira_refs,
)
from src.trec_config import TREC_EDITIONS, selected_editions


LOGGER = logging.getLogger("test_trec")
FIXTURES = Path(__file__).parent / "fixtures"
EDITION = {
    "parent_venue": "TREC",
    "year": 2025,
    "edition": 34,
    "collection_id": "trec2025",
    "proceedings_url": "https://trec.nist.gov/pubs/trec34/index.html",
    "track_url": "https://trec.nist.gov/pubs/trec34/xref.html",
}


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_config_covers_completed_trec_editions():
    assert [edition["year"] for edition in TREC_EDITIONS] == list(range(2025, 1991, -1))
    assert len({edition["edition"] for edition in TREC_EDITIONS}) == 34
    assert selected_editions(2025)[0]["collection_id"] == "trec2025"
    assert selected_editions(2026) == []


def test_parse_modern_nist_track_sections():
    sections = parse_track_page(
        read_fixture("trec_modern_xref.html"),
        "https://trec.nist.gov/pubs/trec34/xref.html",
    )

    assert [section["track_name"] for section in sections] == ["Demo Track", "No Overview Track"]
    assert len(sections[0]["papers"]) == 3
    assert sections[0]["papers"][0]["is_overview"] is True
    assert sections[0]["papers"][0]["pdf_url"].endswith("Overview_demo.pdf")
    assert sections[0]["papers"][1]["team_name"] == "ALPHA"
    assert sections[1]["papers"][0]["is_overview"] is False


def test_parse_legacy_xref_sections():
    sections = parse_track_page(
        read_fixture("trec_legacy_xref.html"),
        "https://trec.nist.gov/pubs/trec26/xref.html",
    )

    assert [section["track_name"] for section in sections] == ["Demo Track", "Other Track"]
    assert len(sections[0]["papers"]) == 3
    assert sections[0]["papers"][0]["is_overview"] is True
    assert sections[0]["papers"][1]["authors"] == ["Alice Alpha"]
    assert sections[1]["papers"][0]["source_format"] == "postscript"
    assert sections[1]["papers"][0]["pdf_url"] is None


def test_parse_early_track_index_prefers_pdf_over_postscript():
    sections = parse_track_page(
        read_fixture("trec_legacy_track.html"),
        "https://trec.nist.gov/pubs/trec9/index.track.html",
    )

    assert len(sections) == 2
    papers = sections[0]["papers"]
    assert len(papers) == 3
    assert papers[0]["source_format"] == "pdf"
    assert papers[0]["title"] == "Overview of the TREC-9 Demo Track"
    assert papers[0]["team_name"] == "Organizer Group"


def test_separately_listed_overview_is_attached_to_matching_track():
    overview_html = """
    <h2>Overview papers</h2>
    <ol><li><a href="papers/Overview_demo.pdf">Overview of the Demo Track</a></li></ol>
    """
    entries = parse_overview_index(overview_html, "https://trec.nist.gov/pubs/trec34/index.html")
    sections = attach_overview_papers([{"track_name": "Demo Track", "papers": []}], entries)

    assert len(entries) == 1
    assert sections[0]["papers"][0]["is_overview"] is True
    assert sections[0]["papers"][0]["pdf_url"].endswith("Overview_demo.pdf")


def test_build_candidate_requires_one_overview_two_unique_pdf_participants():
    sections = parse_track_page(
        read_fixture("trec_modern_xref.html"),
        "https://trec.nist.gov/pubs/trec34/xref.html",
    )
    candidate = build_task_candidate(sections[0], EDITION, set(), set(), [], LOGGER)

    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["screening"]["decision"] == "include"
    assert len(candidate["participants"]) == 2
    assert candidate["task_id"] == "trec2025-demo-track"

    missing = build_task_candidate(sections[1], EDITION, set(), set(), [], LOGGER)
    assert "task_id" not in missing
    assert missing["record_type"] == "unresolved_trec_track"


def test_shared_participant_url_demotes_candidate_and_excludes_shared_paper():
    sections = parse_track_page(
        read_fixture("trec_modern_xref.html"),
        "https://trec.nist.gov/pubs/trec34/xref.html",
    )
    shared = {sections[0]["papers"][1]["source_url"]}
    candidate = build_task_candidate(sections[0], EDITION, shared, set(), [], LOGGER)

    assert candidate["provenance"]["confidence"] == "medium"
    assert len(candidate["participants"]) == 1
    assert "multiple tracks" in " ".join(candidate["provenance"]["confidence_reasons"])


def test_dblp_challenge_or_empty_page_is_non_blocking():
    assert parse_dblp_titles("<html><title>JavaScript challenge</title></html>") == set()


def test_parse_tira_refs_is_supplemental():
    raw = '<a href="/task-overview/trec-demo-2025">TREC Demo Track 2025</a>'
    assert parse_tira_refs(raw, 2025, "Demo Track") == [
        "https://www.tira.io/task-overview/trec-demo-2025"
    ]
