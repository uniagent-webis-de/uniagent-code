import logging
from pathlib import Path

from src.collect_ntcir import (
    build_task_candidate,
    parse_dblp_titles,
    parse_flat_page,
    parse_sectioned_page,
    parse_tira_refs,
    parse_toc_page,
    repair_pdf_url,
)


LOGGER = logging.getLogger("test_ntcir")
FIXTURES = Path(__file__).parent / "fixtures"
EDITION = {
    "parent_venue": "NTCIR",
    "edition": 18,
    "year": 2025,
    "collection_id": "ntcir18",
    "proceedings_url": "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/index.html",
}


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_configured_modern_sections_exclude_general_material_and_poster_links():
    sections = parse_toc_page(
        read_fixture("ntcir_modern_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/NTCIR/toc_ntcir.html",
    )
    assert [section["task_name"] for section in sections] == ["Preface", "Overview", "Demo Task", "Ambiguous Task"]
    assert len(sections[2]["papers"]) == 4
    assert sections[2]["papers"][0]["is_overview"] is True
    assert sections[2]["papers"][0]["authors"] == ["Organizer One"]


def test_legacy_named_sections_parse_li_entries():
    sections = parse_sectioned_page(
        read_fixture("ntcir_legacy_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings9/NTCIR/toc_ntcir.html",
    )
    assert [section["task_name"] for section in sections] == ["GeoTime", "RITE"]
    assert len(sections[0]["papers"]) == 3
    assert sections[0]["papers"][0]["is_overview"] is True


def test_legacy_flat_sections_parse_task_markers():
    sections = parse_toc_page(
        read_fixture("ntcir_legacy_flat_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings4/ntc4-pr-toc.html",
    )
    assert [section["task_name"] for section in sections] == [
        "Cross-Lingual Information Retrieval Task (CLIR)",
        "Patent Retrieval Task",
    ]
    assert len(sections[0]["papers"]) == 3
    assert sections[0]["papers"][0]["is_overview"] is True


def test_flat_ntcir_page_keeps_early_sections_separate():
    sections = parse_flat_page(
        read_fixture("ntcir_flat_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings/index.html",
    )
    assert [section["task_name"] for section in sections] == [
        "IR Tasks (Ad Hoc IR Task and Crosslingual IR Task)",
        "Ad Hoc IR and Cross-lingual",
        "TMREC",
    ]
    assert sections[0]["papers"][0]["is_overview"] is True


def test_build_candidate_requires_one_overview_and_two_participants():
    sections = parse_sectioned_page(
        read_fixture("ntcir_modern_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/NTCIR/toc_ntcir.html",
    )
    candidate = build_task_candidate(sections[2], EDITION, set(), set(), [], LOGGER)
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["screening"]["decision"] == "include"
    assert len(candidate["participants"]) == 2
    assert candidate["task_id"] == "ntcir18-demo-task"
    assert candidate["overview"]["is_umbrella"] is False

    ambiguous = build_task_candidate(sections[3], EDITION, set(), set(), [], LOGGER)
    assert ambiguous["provenance"]["confidence"] == "medium"
    assert "exactly one" in " ".join(ambiguous["provenance"]["confidence_reasons"])


def test_shared_participant_is_excluded_and_demotes_candidate():
    sections = parse_sectioned_page(
        read_fixture("ntcir_modern_toc.html"),
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/NTCIR/toc_ntcir.html",
    )
    shared = {sections[2]["papers"][1]["source_url"]}
    candidate = build_task_candidate(sections[2], EDITION, shared, set(), [], LOGGER)
    assert candidate["provenance"]["confidence"] == "medium"
    assert len(candidate["participants"]) == 1
    assert "multiple task sections" in " ".join(candidate["provenance"]["confidence_reasons"])


def test_no_overview_is_preserved_as_review_record():
    section = {
        "task_name": "No Overview Task",
        "explicit_section": True,
        "papers": [
            {
                "source_id": "a.pdf",
                "source_url": "https://example.org/a.pdf",
                "pdf_url": "https://example.org/a.pdf",
                "source_format": "pdf",
                "title": "Alpha system",
                "authors": [],
                "team_name": None,
                "is_overview": False,
            },
            {
                "source_id": "b.pdf",
                "source_url": "https://example.org/b.pdf",
                "pdf_url": "https://example.org/b.pdf",
                "source_format": "pdf",
                "title": "Beta system",
                "authors": [],
                "team_name": None,
                "is_overview": False,
            },
        ],
    }
    record = build_task_candidate(section, EDITION, set(), set(), [], LOGGER)
    assert record["record_type"] == "unresolved_ntcir_task"
    assert "task_id" not in record


def test_general_proceedings_sections_are_excluded():
    section = {
        "task_name": "Open Submission Papers",
        "explicit_section": True,
        "papers": [
            {
                "source_id": "paper.pdf",
                "source_url": "https://example.org/paper.pdf",
                "pdf_url": "https://example.org/paper.pdf",
                "source_format": "pdf",
                "title": "Overview of an unrelated paper",
                "authors": [],
                "team_name": None,
                "is_overview": True,
            }
        ],
    }
    assert build_task_candidate(section, EDITION, set(), set(), [], LOGGER) is None


def test_dblp_challenge_and_tira_are_supplemental():
    assert parse_dblp_titles("<html><title>Making sure you are not a bot</title></html>") == set()
    raw = '<a href="/task-overview/ntcir-demo-18">NTCIR Demo Task Overview 18</a>'
    assert parse_tira_refs(raw, 18, "Demo Task") == [
        "https://www.tira.io/task-overview/ntcir-demo-18"
    ]


def test_id_headings_and_direct_pdf_anchors_are_supported():
    raw = """
    <h2 id="task-z">Task Z</h2>
    <a class="title">Overview of Task Z</a><br>
    <a href="task-z-overview.pdf">[PDF]</a>
    <span class="author">Organizer Z</span><br>
    <a class="title">Alpha system</a><br>
    <a href="task-z-alpha.pdf">[PDF]</a>
    <span class="author">Alice Alpha</span><br>
    <a class="title">Beta system</a><br>
    <a href="task-z-beta.pdf">[PDF]</a>
    <span class="author">Bob Beta</span>
    """
    sections = parse_sectioned_page(raw, "https://example.org/toc.html")
    assert [section["task_name"] for section in sections] == ["Task Z"]
    assert [paper["title"] for paper in sections[0]["papers"]] == [
        "Overview of Task Z", "Alpha system", "Beta system"
    ]
    assert sections[0]["papers"][0]["authors"] == ["Organizer Z"]


def test_verified_ntcir_pdf_alias_preserves_original_official_href():
    original = "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings12/pdf/ntcir/IMINE/08-NTCIR12-IMINE-SongX.pdf"
    corrected = "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings12/pdf/ntcir/IMINE/08-NTCIR12-IMINE-SongM.pdf"
    assert repair_pdf_url(original) == corrected
    raw = '<h2 id="imine-2">IMine-2</h2><a class="title">IRCE at NTCIR-12 IMine-2 Task</a><a href="' + original + '">[PDF]</a>'
    paper = parse_sectioned_page(raw, "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings12/NTCIR/toc_ntcir.html")[0]["papers"][0]
    assert paper["pdf_url"] == corrected
    assert paper["source_url_original"] == original
