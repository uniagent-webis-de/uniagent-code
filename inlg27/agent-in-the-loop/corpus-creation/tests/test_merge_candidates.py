import json
import logging

from src.merge_candidates import merge


LOGGER = logging.getLogger("test_merge_candidates")


def make_candidate(task_id, confidence="high"):
    return {
        "task_id": task_id,
        "venue": "Test",
        "parent_venue": "Test",
        "year": 2025,
        "task_name": task_id,
        "overview": {"pdf_url": f"https://example.org/{task_id}-overview.pdf"},
        "participants": [{"pdf_url": f"https://example.org/{task_id}-paper.pdf"}],
        "provenance": {"confidence": confidence, "confidence_reasons": []},
    }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_merge_combines_candidates_and_unresolved_review_records(tmp_path, monkeypatch):
    import src.merge_candidates as merger

    candidates_dir = tmp_path / "candidates"
    screening_dir = tmp_path / "screening"
    candidates_dir.mkdir()
    screening_dir.mkdir()
    write_jsonl(candidates_dir / "clef.jsonl", [make_candidate("clef-1")])
    write_jsonl(candidates_dir / "semeval.jsonl", [make_candidate("semeval-1", "medium")])
    write_jsonl(screening_dir / "semeval_review.jsonl", [{"record_type": "unresolved_semeval_task", "task_number": 3}])
    write_jsonl(screening_dir / "semeval_excluded.jsonl", [{"record_type": "excluded", "task_number": 4}])
    monkeypatch.setattr(merger, "CANDIDATES_DIR", candidates_dir)
    monkeypatch.setattr(merger, "SCREENING_DIR", screening_dir)
    monkeypatch.setattr(merger, "INTERMEDIATE_DIR", tmp_path / "intermediate")

    candidates, review, rejected = merge(LOGGER)

    assert [candidate["task_id"] for candidate in candidates] == ["clef-1", "semeval-1"]
    assert any(record.get("task_id") == "semeval-1" for record in review)
    assert any(record.get("record_type") == "unresolved_semeval_task" for record in review)
    assert rejected == [{"record_type": "excluded", "task_number": 4}]


def test_merge_demotes_duplicate_pdf_urls(tmp_path, monkeypatch):
    import src.merge_candidates as merger

    candidates_dir = tmp_path / "candidates"
    screening_dir = tmp_path / "screening"
    candidates_dir.mkdir()
    screening_dir.mkdir()
    left = make_candidate("left")
    right = make_candidate("right")
    right["participants"][0]["pdf_url"] = left["overview"]["pdf_url"]
    write_jsonl(candidates_dir / "source.jsonl", [left, right])
    monkeypatch.setattr(merger, "CANDIDATES_DIR", candidates_dir)
    monkeypatch.setattr(merger, "SCREENING_DIR", screening_dir)

    candidates, review, _ = merge(LOGGER)

    assert all(candidate["provenance"]["confidence"] == "medium" for candidate in candidates)
    assert len(review) == 2


def test_merge_allows_explicitly_shared_sisap_documents(tmp_path, monkeypatch):
    import src.merge_candidates as merger

    candidates_dir = tmp_path / "candidates"
    screening_dir = tmp_path / "screening"
    candidates_dir.mkdir()
    screening_dir.mkdir()
    left = make_candidate("sisap2024-task-1")
    right = make_candidate("sisap2024-task-2")
    for candidate in (left, right):
        candidate["parent_venue"] = "SISAP"
        candidate["overview"]["pdf_url"] = "https://example.org/shared-overview.pdf"
        candidate["overview"]["shared_document_id"] = "sisap2024:overview"
        candidate["overview"]["shared_document_group"] = "sisap2024"
        candidate["participants"][0]["pdf_url"] = "https://example.org/shared-paper.pdf"
        candidate["participants"][0]["shared_document_id"] = "sisap2024:paper"
        candidate["participants"][0]["shared_document_group"] = "sisap2024"
    write_jsonl(candidates_dir / "sisap.jsonl", [left, right])
    monkeypatch.setattr(merger, "CANDIDATES_DIR", candidates_dir)
    monkeypatch.setattr(merger, "SCREENING_DIR", screening_dir)

    candidates, review, _ = merge(LOGGER)

    assert all(candidate["provenance"]["confidence"] == "high" for candidate in candidates)
    assert review == []


def test_merge_ignores_stale_failure_for_replaced_pdf_url(tmp_path, monkeypatch):
    import src.merge_candidates as merger

    candidates_dir = tmp_path / "candidates"
    screening_dir = tmp_path / "screening"
    intermediate_dir = tmp_path / "intermediate"
    candidates_dir.mkdir()
    screening_dir.mkdir()
    candidate = make_candidate("sisap2023-task-a")
    candidate["parent_venue"] = "SISAP"
    current_url = candidate["participants"][0]["pdf_url"]
    write_jsonl(
        candidates_dir / "sisap.jsonl",
        [candidate],
    )
    failure_path = intermediate_dir / "download_failures.jsonl"
    write_jsonl(
        failure_path,
        [{"task_id": candidate["task_id"], "pdf_url": "https://example.org/old-paper.pdf"}],
    )
    monkeypatch.setattr(merger, "CANDIDATES_DIR", candidates_dir)
    monkeypatch.setattr(merger, "SCREENING_DIR", screening_dir)
    monkeypatch.setattr(merger, "DOWNLOAD_FAILURES_PATH", failure_path)

    candidates, review, _ = merge(LOGGER)

    assert candidates[0]["participants"][0]["pdf_url"] == current_url
    assert candidates[0]["provenance"]["confidence"] == "high"
    assert review == []
