import logging

import pytest

from src import collect_acl
from src.acl_config import ACL_TASKS, selected_tasks, selected_volumes, volume_url
from src.collect_acl import (
    assignment_method, build_candidate, collect_all, parse_volume, select_participants, task_id_for,
)


LOGGER = logging.getLogger("test_acl")
COLLECTION = "X20-1"


def entry(paper_id, title, authors=("Ann Author",), pdf=True):
    pdf_link = f'<a class="badge" href="https://aclanthology.org/{paper_id}.pdf">pdf</a>' if pdf else ""
    people = "".join(f'<a href="/people/{a.lower().replace(" ", "-")}/">{a}</a>' for a in authors)
    return (
        f'<div class="row">{pdf_link}<span><strong>'
        f'<a class="align-middle" href="/{paper_id}/">{title}</a></strong>{people}</span></div>'
    )


SAMPLE_HTML = "<html><body>" + "".join([
    entry("X20-1000", "Proceedings of the Shared Task"),
    entry("X20-1001", "The <span>Foo</span> 2020 Shared Task on Bar"),
    entry("X20-1002", "Team A at Foo 2020 Task 1: A system"),
    entry("X20-1003", "An unrelated workshop paper"),
    entry("X20-1004", "Team B at Foo 2020 Task 1: Another system"),
    entry("X20-1005", "Team C at Foo 2020 Task 2: Other task"),
    entry("X20-1006", "The Foo 2020 Shared Task on Baz"),
]) + "</body></html>"


def make_task(**rule):
    task = {
        "venue": "Foo", "parent_venue": "Foo", "year": 2020, "collection_id": COLLECTION,
        "overview_id": "X20-1001", "task_name": "Bar", "provider": "acl_anthology",
        "first": None, "last": None, "match": None, "exclude": [],
    }
    task.update(rule)
    return task


def test_parse_volume_skips_front_matter_and_keeps_title_spacing_and_pdf_links():
    papers = parse_volume(SAMPLE_HTML, COLLECTION)
    assert [p["source_id"] for p in papers][0] == "X20-1001"
    assert papers[0]["title"] == "The Foo 2020 Shared Task on Bar"
    assert papers[0]["pdf_url"] == "https://aclanthology.org/X20-1001.pdf"
    assert papers[0]["authors"] == ["Ann Author"]


def test_a_real_paper_whose_id_ends_in_00_is_not_front_matter():
    html = entry("X20-1100", "A real system paper")
    assert [p["source_id"] for p in parse_volume(html, COLLECTION)] == ["X20-1100"]


def test_select_participants_applies_range_marker_and_other_overviews():
    papers = parse_volume(SAMPLE_HTML, COLLECTION)
    overviews = {"X20-1001", "X20-1006"}
    marked = make_task(match=r"\bTask 1\b")
    assert [p["source_id"] for p in select_participants(marked, papers, overviews)] == ["X20-1002", "X20-1004"]
    ranged = make_task(first="X20-1002", last="X20-1004", exclude=["X20-1003"])
    assert [p["source_id"] for p in select_participants(ranged, papers, overviews)] == ["X20-1002", "X20-1004"]
    whole = make_task()
    assert "X20-1006" not in [p["source_id"] for p in select_participants(whole, papers, overviews)]


def test_unknown_range_endpoint_fails_loudly():
    papers = parse_volume(SAMPLE_HTML, COLLECTION)
    with pytest.raises(ValueError):
        select_participants(make_task(first="X20-9999"), papers, set())


def test_assignment_method_names_the_evidence():
    assert assignment_method(make_task()) == "dedicated_volume"
    assert assignment_method(make_task(first="X20-1002")) == "curated_range"
    assert assignment_method(make_task(first="X20-1002", match="x")) == "title_marker"


def test_build_candidate_is_high_confidence_with_two_participants():
    papers = parse_volume(SAMPLE_HTML, COLLECTION)
    candidate = build_candidate(make_task(match=r"\bTask 1\b"), papers, {"X20-1001"}, LOGGER)
    assert candidate["task_id"] == "foo2020-bar" == task_id_for(make_task())
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["provenance"]["task_assignment_method"] == "title_marker"
    assert candidate["overview"]["pdf_url"].endswith("X20-1001.pdf")
    assert len(candidate["participants"]) == 2
    assert candidate["counts"]["notebook_papers"] == 2


def test_build_candidate_demotes_small_groups_and_rejects_a_missing_overview():
    papers = parse_volume(SAMPLE_HTML, COLLECTION)
    small = build_candidate(make_task(match=r"\bTask 2\b"), papers, set(), LOGGER)
    assert small["provenance"]["confidence"] == "medium"
    assert "found only 1 participant papers" in small["provenance"]["confidence_reasons"]
    assert build_candidate(make_task(overview_id="X20-9999"), papers, set(), LOGGER) is None


def test_collect_all_writes_candidates_from_cached_pages(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / f"{COLLECTION}.html").write_text(SAMPLE_HTML, encoding="utf-8")
    monkeypatch.setattr(collect_acl, "selected_tasks", lambda year: [make_task(match=r"\bTask 1\b")])
    monkeypatch.setattr(collect_acl, "CANDIDATES_DIR", tmp_path / "candidates")
    monkeypatch.setattr(collect_acl, "SCREENING_DIR", tmp_path / "screening")

    assert collect_all(None, LOGGER, raw_dir)
    assert (tmp_path / "candidates" / "acl.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert collect_all(None, LOGGER, tmp_path / "missing") is False


def test_configured_tasks_are_unique_and_never_share_an_overview():
    ids = [task_id_for(task) for task in ACL_TASKS]
    assert len(ids) == len(set(ids))
    overviews = [task["overview_id"] for task in ACL_TASKS]
    assert len(overviews) == len(set(overviews))


def test_selected_volumes_cover_every_task_and_urls_are_official():
    assert set(selected_volumes()) == {task["collection_id"] for task in ACL_TASKS}
    assert selected_tasks(1900) == []
    assert volume_url("W14-17") == "https://aclanthology.org/volumes/W14-17/"


def test_inlg_feedback_generation_keeps_the_task_year_and_papers_on_both_sides_of_overview():
    task = next(task for task in selected_tasks(2022) if task["overview_id"] == "2023.inlg-genchal.7")
    ids = [f"2023.inlg-genchal.{number}" for number in range(4, 14)]
    papers = parse_volume("".join(entry(paper_id, f"Paper {paper_id}") for paper_id in ids),
                          task["collection_id"])
    candidate = build_candidate(task, papers, {task["overview_id"]}, LOGGER)
    assert candidate["year"] == 2022
    assert candidate["parent_venue"] == "INLG"
    assert candidate["provenance"]["confidence"] == "high"
    assert [paper["source_id"] for paper in candidate["participants"]] == ids[1:3] + ids[4:9]
