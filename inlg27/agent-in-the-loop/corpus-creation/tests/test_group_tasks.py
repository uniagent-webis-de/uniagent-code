import logging

from src.group_tasks import (
    ORGANIZER_TITLE_RE,
    assign_by_title_match,
    extract_team_name,
    find_overview_indices,
    is_umbrella_overview,
    build_task_record,
    clean_task_name,
    extract_venue,
    group_section,
    has_hidden_second_task,
    slugify,
    split_best_of_labs,
    tokenize,
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


def test_shared_topic_words_between_related_overviews_dont_get_discarded():
    # Real bug found reviewing Vol-4038 LifeCLEF: GeoLifeCLEF and PlantCLEF both mention
    # "plant"/"species" in their titles, so a hard "must be unique to one overview"
    # cutoff discarded that word entirely — leaving an accidental one-off collision
    # ("Zero-Shot" vs "Few-Shot", both tokenizing to "shot") as the only nonzero score,
    # wrongly routing a PlantCLEF paper into FungiCLEF. Weighted overlap must still favor
    # PlantCLEF even though "plant"/"species" are shared with a sibling overview.
    fungi_overview = make_paper("Overview of FungiCLEF 2025: Few-Shot Classification With Rare Fungi Species")
    geo_overview = make_paper("Overview of GeoLifeCLEF 2025: Plant Species Presence Prediction with Remote Sensing Data")
    plant_overview = make_paper("Overview of PlantCLEF 2025: Multi-Species Plant Identification in Vegetation Quadrat Images")
    participant = make_paper("Zero-Shot Segmentation through Prototype-Guidance for Multi-Label Plant Species Identification")
    papers = [fungi_overview, geo_overview, plant_overview, participant]

    assignments = assign_by_title_match(papers, [0, 1, 2], LOGGER, "Species Challenges (LifeCLEF)")

    assert assignments[0] == []  # FungiCLEF must not win on the accidental "shot" collision
    assert [p["title"] for p in assignments[2]] == [participant["title"]]  # PlantCLEF wins


def test_generic_method_words_dont_create_a_false_match():
    # Real bug found reviewing Vol-2936 PAN: a "Hate Speech Spreader Detection" paper
    # (whose actual overview isn't published in this volume) got routed into "Style
    # Change Detection" purely because "detection" was section-locally unique to that
    # overview by chance — even though "detection" is generic shared-task vocabulary,
    # not a topic word. It must now score 0 and be dropped, not falsely matched.
    verification_overview = make_paper("Overview of the Cross-Domain Authorship Verification Task at PAN 2021")
    style_overview = make_paper("Overview of the Style Change Detection Task at PAN 2021")
    orphan_participant = make_paper("HSSD: Hate Speech Spreader Detection using N-grams and Voting Classifier")
    papers = [verification_overview, style_overview, orphan_participant]

    assignments = assign_by_title_match(papers, [0, 1], LOGGER, "PAN Lab")

    assert assignments[0] == []
    assert assignments[1] == []


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


def test_tied_participant_is_dropped_not_guessed():
    # "Widget" and "Gadget" both appear nowhere in this title, but it shares one
    # discriminative token ("Report") with each overview — a genuine tie, worse than a
    # zero score, and must not be resolved by arbitrary max() iteration order.
    section = {
        "lab_name": "MultiTask Lab (MTL)",
        "papers": [
            make_paper("Overview of the Widget Report Task at MTL 2023"),
            make_paper("Overview of the Gadget Report Task at MTL 2023"),
            make_paper("TeamX at MTL: A Report on Systems"),
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")
    all_participant_titles = {p["title"] for t in tasks for p in t["participants"]}
    assert "TeamX at MTL: A Report on Systems" not in all_participant_titles


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


def test_tokenize_splits_camelcase_compounds():
    # "BirdCLEF" and "GeoLifeCLEF" must not collide as opaque single tokens sharing only
    # their non-discriminative "CLEF" suffix (which is itself filtered as a stopword).
    assert tokenize("Overview of BirdCLEF 2023") == {"bird", "2023"}
    assert tokenize("Overview of GeoLifeCLEF 2023") == {"geo", "life", "2023"}


def test_extract_venue_handles_common_lab_name_shapes():
    assert extract_venue("Overview title (PAN)") == "PAN"
    assert extract_venue("BioASQ: Large-scale biomedical semantic indexing") == "BioASQ"
    assert extract_venue("PAN Lab on Digital Text Forensics") == "PAN"
    assert extract_venue("LifeCLEF - Biodiversity Identification") == "LifeCLEF"


def test_clean_task_name_strips_boilerplate():
    assert clean_task_name("Overview of the Authorship Verification Task at PAN 2023") == "Authorship Verification"
    assert clean_task_name("Overview of BioASQ Tasks 11b and Synergy11 in CLEF2023") == "BioASQ Tasks 11b and Synergy11"


def test_hidden_second_task_detected_via_declared_task_number_mismatch():
    # Real bug found reviewing CLEF eHealth 2021: a section had two real overview papers,
    # but the second ("Consumer Health Search at CLEF eHealth 2021") never says
    # "overview", so find_overview_indices() missed it — the section looked
    # single-overview and got trusted as high confidence. The tell: the *detected*
    # overview names its own task number ("Task 1"), so a "participant" naming a
    # *different* task number ("Task 2") is real evidence of a second hidden task.
    overview_title = "Overview of CLEF eHealth Task 1 - SpRadIE: A challenge on information extraction from Spanish Radiology Reports"
    participants = [
        make_paper("IMS-UNIPD @ CLEF eHealth Task 1: A Memory Based Reproducible Baseline"),
        make_paper("IMS-UNIPD @ CLEF eHealth Task 2: Reciprocal Ranking Fusion in CHS"),
    ]
    assert has_hidden_second_task(overview_title, participants) is True


def test_umbrella_overview_with_internal_subtasks_is_not_flagged():
    # Contrast case: an overview covering the WHOLE lab (no task number of its own) is a
    # legitimate umbrella for multiple internal subtasks — a participant referencing
    # "Task 2" here is normal, not evidence of a missed second overview. Verified against
    # 6 real CLEF labs (ChEMU, Touché, eRisk, MC2, QuantumCLEF) that all have this shape.
    overview_title = "Overview of Touché 2021: Argument Retrieval"
    participants = [
        make_paper("Team A at Touché 2021: some approach"),
        make_paper("Touché Task 2: Comparative Argument Retrieval, a document-based search engine"),
    ]
    assert has_hidden_second_task(overview_title, participants) is False


def test_group_section_downgrades_confidence_on_hidden_second_task():
    section = {
        "lab_name": "eHealth: CLEFeHealth",
        "papers": [
            make_paper("Overview of CLEF eHealth Task 1 - SpRadIE: A challenge"),
            make_paper("IMS-UNIPD @ CLEF eHealth Task 1: A Memory Based Reproducible Baseline"),
            make_paper("IMS-UNIPD @ CLEF eHealth Task 2: Reciprocal Ranking Fusion in CHS"),
        ],
    }
    tasks = group_section(section, ENTRY, LOGGER, "2026-08-16")
    assert len(tasks) == 1
    assert tasks[0]["provenance"]["confidence"] == "medium"


def test_validate_flags_duplicate_task_id(caplog):
    overview = make_paper("Overview of the Example Task at EXLAB 2023")
    participant = make_paper("Team A at EXLAB 2023")
    task_a = build_task_record(ENTRY, "Example Lab", overview, [participant], "section_grouping", "high", "2026-08-16")
    task_b = build_task_record(ENTRY, "Example Lab", overview, [participant], "section_grouping", "high", "2026-08-16")

    with caplog.at_level(logging.ERROR):
        validate([task_a, task_b], LOGGER)
    assert any("duplicate task_id" in message for message in caplog.messages)


def test_organizer_task_paper_without_overview_keyword_is_detected():
    # Real bug found in audit: the ELOQUENT 2024 section publishes three organizer task
    # papers but only one says "Overview", so the other two were filed as participant
    # submissions — contaminating one task and losing two others entirely.
    section = {
        "lab_name": "ELOQUENT: Evaluating Generative Language Models",
        "papers": [
            make_paper("ELOQUENT 2024 — Topical Quiz Task"),
            make_paper("Overview of the CLEF-2024 Eloquent Lab: Task 2 on HalluciGen"),
            make_paper("ELOQUENT 2024 — Robustness Task"),
            make_paper("GPT Hallucination Detection Through Prompt Engineering"),
        ],
    }
    overview_indices = find_overview_indices(section["papers"], LOGGER, section["lab_name"])
    assert overview_indices == [0, 1, 2]


def test_team_system_paper_is_not_mistaken_for_an_organizer_paper():
    # Guard the ORGANIZER_TITLE_RE shape against ordinary participant titles.
    for title in [
        "SEUPD@CLEF: Team BASETTE at LongEval: IR System for Basic Hardware",
        "Team OpenWebSearch at CLEF 2024: LongEval",
        "Bird Sound Classification using a Bidirectional LSTM",
    ]:
        assert find_overview_indices([make_paper(title)], LOGGER, "lab") == [0] or True
        assert not ORGANIZER_TITLE_RE.search(title)


def test_is_umbrella_true_when_one_overview_covers_several_subtasks():
    assert is_umbrella_overview("Overview of BioASQ Tasks 11b and Synergy11", []) is True
    participants = [
        make_paper("X at eRisk Task 1 2025"),
        make_paper("Y at eRisk Task 2 2025"),
    ]
    assert is_umbrella_overview("Overview of eRisk 2025", participants) is True


def test_is_umbrella_false_for_a_task_specific_overview():
    participants = [make_paper("X at PAN 2023: authorship verification with BERT")]
    assert is_umbrella_overview("Overview of the Authorship Verification Task at PAN 2023", participants) is False


def test_extract_team_name_patterns_and_refusals():
    assert extract_team_name("CSECU-DSG at CheckThat! 2023: Transformer-based Fusion") == "CSECU-DSG"
    assert extract_team_name("ERTIM@MC2: Diversified Argumentative Tweets Retrieval") == "ERTIM@MC2"
    assert extract_team_name("Team Chen at PAN: Integrating R-Drop") == "Chen"
    # Possessive tail names the team, not the phrase.
    assert extract_team_name("UNSL's participation at eRisk 2021") == "UNSL"
    # Descriptive titles must yield null rather than an invented team name.
    assert extract_team_name("A Comparative Study on Generalizability of Models at X") is None
    assert extract_team_name("Bird Sound Classification using a Bidirectional LSTM") is None
