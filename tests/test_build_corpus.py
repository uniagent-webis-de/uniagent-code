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
