import logging

from src.group_tasks import (
    build_task_record,
    clean_task_name,
    extract_venue,
    group_section,
    slugify,
    split_best_of_labs,
    validate,
)

ENTRY = {"parent_venue": "CLEF", "year": 2023, "volume": "9999"}
LOGGER = logging.getLogger("test")


def make_paper(title, pdf_url=None, authors=None):
    return {
        "title": title,
        "authors": authors or ["Test Author"],
        "pdf_url": pdf_url or f"https://ceur-ws.org/Vol-9999/{slugify(title)}.pdf",
        "position_in_section": 0,
        "dblp_match": True,
    }


def test_single_overview_section_uses_positional_grouping():
    section = {
        "lab_name": "Example Lab (EXLAB)",
        "papers": [
            make_paper("Overview of the Example Task at EXLAB 2023"),
            make_paper("Team A at EXLAB 2023"),
            make_paper("Team B at EXLAB 2023"),
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")

    assert len(tasks) == 1
    assert tasks[0]["provenance"]["task_assignment_method"] == "section_grouping"
    assert tasks[0]["provenance"]["confidence"] == "high"
    assert len(tasks[0]["participants"]) == 2


def test_multi_overview_section_assigns_by_title_keyword_overlap():
    # Mirrors the real CEUR-WS pattern: both overviews listed first, participants
    # interleaved afterward rather than grouped contiguously per task.
    section = {
        "lab_name": "Overview of MultiTask Lab (MTL)",
        "papers": [
            make_paper("Overview of the Widget Detection Task at MTL 2023"),
            make_paper("Overview of the Gadget Classification Task at MTL 2023"),
            make_paper("TeamX at MTL: Widget Detection with Transformers"),
            make_paper("TeamY at MTL: Gadget Classification via CNNs"),
            make_paper("TeamZ at MTL: Another Widget Detection Approach"),
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")

    assert len(tasks) == 2
    widget_task = next(t for t in tasks if "Widget" in t["task_name"])
    gadget_task = next(t for t in tasks if "Gadget" in t["task_name"])

    assert {p["title"] for p in widget_task["participants"]} == {
        "TeamX at MTL: Widget Detection with Transformers",
        "TeamZ at MTL: Another Widget Detection Approach",
    }
    assert {p["title"] for p in gadget_task["participants"]} == {
        "TeamY at MTL: Gadget Classification via CNNs",
    }
    for t in tasks:
        assert t["provenance"]["task_assignment_method"] == "title_heuristic"
        assert t["provenance"]["confidence"] == "medium"


def test_ambiguous_participant_is_dropped_not_guessed():
    section = {
        "lab_name": "MultiTask Lab (MTL)",
        "papers": [
            make_paper("Overview of the Widget Detection Task at MTL 2023"),
            make_paper("Overview of the Gadget Classification Task at MTL 2023"),
            make_paper("TeamX at MTL: Widget Detection with Transformers"),
            make_paper("Is ChatGPT an MTL Expert?"),  # shares no discriminative keyword with either overview
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")
    all_participant_titles = {p["title"] for t in tasks for p in t["participants"]}
    assert "Is ChatGPT an MTL Expert?" not in all_participant_titles


def test_zero_participant_task_is_rejected():
    section = {
        "lab_name": "Lonely Lab (LL)",
        "papers": [make_paper("Overview of the Lonely Task at LL 2023")],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")
    assert tasks == []


def test_best_of_labs_papers_excluded():
    papers = [
        make_paper("Overview of the Example Task at EXLAB 2023"),
        make_paper("Team A at EXLAB 2023"),
        make_paper("EXLAB 2022 Best of Labs: A Retrospective"),
    ]
    kept, excluded = split_best_of_labs(papers, LOGGER)
    assert len(excluded) == 1
    assert excluded[0]["title"].startswith("EXLAB 2022 Best of Labs")
    assert all("Best of Labs" not in p["title"] for p in kept)


def test_no_overview_keyword_falls_back_to_first_paper():
    section = {
        "lab_name": "Odd Lab (ODD)",
        "papers": [
            make_paper("ODD 2023: A Technical Summary of the Shared Task"),
            make_paper("Team A at ODD 2023"),
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")
    assert len(tasks) == 1
    assert tasks[0]["overview"]["title"] == "ODD 2023: A Technical Summary of the Shared Task"


def test_extract_venue_handles_common_lab_name_shapes():
    assert extract_venue("Overview title (PAN)") == "PAN"
    assert extract_venue("BioASQ: Large-scale biomedical semantic indexing") == "BioASQ"
    assert extract_venue("PAN Lab on Digital Text Forensics") == "PAN"
    assert extract_venue("LifeCLEF - Biodiversity Identification") == "LifeCLEF"


def test_clean_task_name_strips_boilerplate():
    assert clean_task_name("Overview of the Authorship Verification Task at PAN 2023") == "Authorship Verification"
    assert clean_task_name("Overview of BioASQ Tasks 11b and Synergy11 in CLEF2023") == "BioASQ Tasks 11b and Synergy11"


def test_validate_flags_duplicate_task_id(caplog):
    overview = make_paper("Overview of the Example Task at EXLAB 2023")
    participant = make_paper("Team A at EXLAB 2023")
    task_a = build_task_record(ENTRY, "Example Lab", overview, [participant], "section_grouping", "high", "2026-08-16")
    task_b = build_task_record(ENTRY, "Example Lab", overview, [participant], "section_grouping", "high", "2026-08-16")

    with caplog.at_level(logging.ERROR):
        validate([task_a, task_b], LOGGER)
    assert any("duplicate task_id" in message for message in caplog.messages)
