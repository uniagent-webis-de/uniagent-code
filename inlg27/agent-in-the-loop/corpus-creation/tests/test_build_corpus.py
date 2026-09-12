import logging

from src.build_corpus import validate

LOGGER = logging.getLogger("test")


def make_task(task_id, overview_pdf_url, participant_pdf_urls, coverage_ratio=1.0):
    return {
        "task_id": task_id,
        "overview": {"pdf_url": overview_pdf_url, "title": "Overview", "authors": [], "is_umbrella": False},
        "participants": [
            {"title": "P", "authors": [], "pdf_url": url, "team_name": None, "code_urls": [], "tira_refs": []}
            for url in participant_pdf_urls
        ],
        "counts": {"notebook_papers": len(participant_pdf_urls), "teams_claimed_in_overview": None, "runs_claimed_in_overview": None, "coverage_ratio": coverage_ratio},
        "provenance": {"task_assignment_method": "section_grouping", "confidence": "high", "extracted_at": "2026-08-16"},
    }


def test_valid_corpus_passes():
    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf", "p2.pdf"]),
        make_task("t2", "ov2.pdf", ["p3.pdf"]),
    ]
    assert validate(tasks, LOGGER) is True


def test_duplicate_task_id_fails(caplog):
    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t1", "ov2.pdf", ["p2.pdf"]),
    ]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("duplicate task_id" in m for m in caplog.messages)


def test_duplicate_pdf_url_across_tasks_fails(caplog):
    tasks = [
        make_task("t1", "ov1.pdf", ["shared.pdf"]),
        make_task("t2", "ov2.pdf", ["shared.pdf"]),
    ]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("duplicate pdf_url" in m for m in caplog.messages)


def test_explicitly_shared_sisap_document_is_allowed(caplog):
    tasks = [
        make_task("sisap-task-1", "shared-overview.pdf", ["shared-paper.pdf"]),
        make_task("sisap-task-2", "shared-overview.pdf", ["shared-paper.pdf"]),
    ]
    for task in tasks:
        task["parent_venue"] = "SISAP"
        task["overview"]["shared_document_id"] = "sisap:overview"
        task["overview"]["shared_document_group"] = "sisap2025"
        task["participants"][0]["shared_document_id"] = "sisap:paper"
        task["participants"][0]["shared_document_group"] = "sisap2025"
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is True
    assert not any("duplicate pdf_url" in m for m in caplog.messages)


def test_zero_participants_fails(caplog):
    tasks = [make_task("t1", "ov1.pdf", [])]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("0 participants" in m for m in caplog.messages)


def test_coverage_ratio_out_of_bounds_fails(caplog):
    tasks = [make_task("t1", "ov1.pdf", ["p1.pdf"], coverage_ratio=3.5)]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("outside [0, 1.5]" in m for m in caplog.messages)


def test_null_coverage_ratio_is_allowed():
    tasks = [make_task("t1", "ov1.pdf", ["p1.pdf"], coverage_ratio=None)]
    assert validate(tasks, LOGGER) is True


def test_final_task_directories_match_the_assembled_tasks(tmp_path, monkeypatch):
    from src import build_corpus

    final_dir = tmp_path / "final"
    (final_dir / "t1").mkdir(parents=True)
    (final_dir / "stale-task").mkdir()
    monkeypatch.setattr(build_corpus, "FINAL_DIR", final_dir)

    assert build_corpus.validate_final_task_directories(
        [make_task("t1", "ov1.pdf", ["p1.pdf"])], LOGGER
    ) is False


def test_final_task_directory_validation_rejects_missing_directory(tmp_path, monkeypatch):
    from src import build_corpus

    final_dir = tmp_path / "final"
    final_dir.mkdir()
    monkeypatch.setattr(build_corpus, "FINAL_DIR", final_dir)

    assert build_corpus.validate_final_task_directories(
        [make_task("t1", "ov1.pdf", ["p1.pdf"])], LOGGER
    ) is False


def test_select_corpus_emits_all_candidates_without_a_target_cap():
    from src.build_corpus import select_corpus

    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t2", "ov2.pdf", ["p2.pdf"]),
    ]
    selected = select_corpus(tasks, None, LOGGER)
    assert {task["task_id"] for task in selected} == {"t1", "t2"}


def test_select_corpus_keeps_optional_target_cap():
    from src.build_corpus import select_corpus

    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t2", "ov2.pdf", ["p2.pdf"]),
    ]
    assert len(select_corpus(tasks, 1, LOGGER)) == 1


def test_fulltext_paths_are_published_on_the_records():
    # Consumers must be able to go from a corpus entry straight to its parsed text,
    # rather than deriving filenames from pdf_url by string manipulation.
    from src.build_corpus import join_fulltext_paths

    task = make_task("t1", "https://x/ov.pdf", ["https://x/p1.pdf", "https://x/p2.pdf"])
    manifest = {
        "https://x/ov.pdf": {
            "pdf_path": "data/final/t1/overview/overview.pdf",
            "markdown_path": "data/final/t1/overview/overview.txt.md",
            "n_figures": 0,
            "n_tables": 3,
        },
        "https://x/p1.pdf": {
            "pdf_path": "data/final/t1/papers/p1/paper.pdf",
            "markdown_path": "data/final/t1/papers/p1/paper.txt.md",
            "n_figures": 2,
            "n_tables": 1,
        },
    }
    join_fulltext_paths(task, manifest, LOGGER)

    assert task["overview"]["pdf_path"] == "data/final/t1/overview/overview.pdf"
    assert task["overview"]["fulltext_path"] == "data/final/t1/overview/overview.txt.md"
    assert task["participants"][0]["pdf_path"] == "data/final/t1/papers/p1/paper.pdf"
    assert task["participants"][0]["fulltext_path"] == "data/final/t1/papers/p1/paper.txt.md"
    # An unparsed document yields null rather than a fabricated path.
    assert task["participants"][1]["fulltext_path"] is None
    # Figure/table counts ride along so they are queryable from the corpus files.
    assert task["overview"]["n_tables"] == 3
    assert task["participants"][0]["n_figures"] == 2
    assert task["participants"][1]["n_figures"] == 0


def test_fulltext_join_is_a_no_op_when_stage_7_has_not_run():
    from src.build_corpus import join_fulltext_paths

    task = make_task("t1", "https://x/ov.pdf", ["https://x/p1.pdf"])
    join_fulltext_paths(task, {}, LOGGER)
    assert "fulltext_path" not in task["overview"]
