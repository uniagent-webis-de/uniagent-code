import logging
from pathlib import Path

from src.collect_semeval import build_task_candidate, collect_volume, parse_papers


LOGGER = logging.getLogger("test_semeval")
VOLUME = {
    "venue": "SemEval",
    "year": 2025,
    "collection_id": "2025.semeval-1",
    "url": "https://aclanthology.org/volumes/2025.semeval-1/",
    "provider": "acl_anthology",
}

SAMPLE_HTML = """
<html><body>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.1/">SemEval-2025 Task 1: Idiomaticity</a>
    <a href="/2025.semeval-1.1.pdf">pdf</a>
    <a href="/people/organizer/">Organizer One</a>
  </div>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.2/">AlphaatSemEval-2025 Task 1: A system</a>
    <a href="/2025.semeval-1.2.pdf">pdf</a>
    <a href="/people/alpha/">Alpha Author</a>
  </div>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.3/">Beta at SemEval-2025 Task 1: Another system</a>
    <a href="/2025.semeval-1.3.pdf">pdf</a>
    <a href="/people/beta/">Beta Author</a>
  </div>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.4/">SemEval-2025 Task 2: Small task</a>
    <a href="/2025.semeval-1.4.pdf">pdf</a>
    <a href="/people/organizer2/">Organizer Two</a>
  </div>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.5/">GammaatSemEval-2025 Task 2: One system</a>
    <a href="/2025.semeval-1.5.pdf">pdf</a>
    <a href="/people/gamma/">Gamma Author</a>
  </div>
  <div class="paper">
    <a class="align-middle" href="/2025.semeval-1.6/">NoTask atSemEval-2025</a>
    <a href="/2025.semeval-1.6.pdf">pdf</a>
    <a href="/people/no-task/">No Task Author</a>
  </div>
</body></html>
"""


def test_parse_papers_handles_compact_acl_participant_titles():
    papers = parse_papers(SAMPLE_HTML, VOLUME)

    assert len(papers) == 6
    organizer, compact, spaced, *_ = papers
    assert organizer["task_number"] == 1
    assert organizer["is_organizer"] is True
    assert organizer["is_participant"] is False
    assert compact["task_number"] == 1
    assert compact["is_participant"] is True
    assert spaced["is_participant"] is True
    assert spaced["pdf_url"] == "https://aclanthology.org/2025.semeval-1.3.pdf"
    assert compact["authors"] == ["Alpha Author"]


def test_build_task_candidate_is_high_only_with_strong_evidence():
    papers = parse_papers(SAMPLE_HTML, VOLUME)
    task_one = [paper for paper in papers if paper["task_number"] == 1]
    candidate = build_task_candidate(task_one, VOLUME, LOGGER)

    assert candidate is not None
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["screening"]["decision"] == "include"
    assert len(candidate["participants"]) == 2
    assert candidate["participants"][0]["team_name"] == "Alpha"


def test_build_task_candidate_demotes_small_groups_and_rejects_missing_overview():
    papers = parse_papers(SAMPLE_HTML, VOLUME)
    task_two = [paper for paper in papers if paper["task_number"] == 2]
    candidate = build_task_candidate(task_two, VOLUME, LOGGER)
    assert candidate["provenance"]["confidence"] == "medium"
    assert "found only 1 explicit participant papers" in candidate["provenance"]["confidence_reasons"]

    participant_only = [paper for paper in papers if paper["source_id"] == "2025.semeval-1.6"]
    assert build_task_candidate(participant_only, VOLUME, LOGGER) is None


def test_collect_volume_keeps_unassigned_papers_for_review(tmp_path, monkeypatch):
    from src import collect_semeval

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "2025.semeval-1.html").write_text(SAMPLE_HTML, encoding="utf-8")
    monkeypatch.setattr(collect_semeval, "RAW_DIR", raw_dir)

    candidates, review, excluded, unassigned = collect_volume(VOLUME, LOGGER)

    assert len(candidates) == 2
    assert len(excluded) == 0
    assert unassigned == 1
    assert any(record["record_type"] == "unassigned_semeval_paper" for record in review)
