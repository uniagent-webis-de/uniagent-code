import logging

from src import download_papers
from src.candidate_schema import read_jsonl, write_jsonl
from src.corpus_paths import document_pdf_path


class FakeResponse:
    status_code = 200
    content = b"%PDF-1.7\nminimal test pdf"


def test_download_pdf_writes_a_valid_cache_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(download_papers.requests, "get", lambda *args, **kwargs: FakeResponse())
    destination = tmp_path / "task" / "overview.pdf"

    assert download_papers.download_pdf("https://example.test/paper.pdf", destination, logging.getLogger("test"))
    assert download_papers.is_valid_pdf(destination)
    assert list(destination.parent.glob("*.tmp")) == []


def test_download_pdf_reuses_existing_cache_without_network(tmp_path, monkeypatch):
    destination = tmp_path / "paper.pdf"
    destination.write_bytes(FakeResponse.content)

    def unexpected_request(*args, **kwargs):
        raise AssertionError("a valid cached PDF must not be fetched again")

    monkeypatch.setattr(download_papers.requests, "get", unexpected_request)
    assert download_papers.download_pdf("https://example.test/paper.pdf", destination, logging.getLogger("test"))


def test_process_document_uses_the_agreed_path(monkeypatch, tmp_path):
    destinations = []
    monkeypatch.setattr(download_papers, "download_pdf", lambda url, destination, logger: destinations.append(destination) or True)

    assert download_papers.process_document("task", "participant", "https://x/paper-1.pdf", logging.getLogger("test"))
    expected = document_pdf_path("task", "participant", "https://x/paper-1.pdf")
    assert destinations == [expected]


def test_process_documents_runs_overview_and_participant_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        download_papers,
        "process_document",
        lambda task_id, role, url, logger: calls.append((task_id, role, url)) or True,
    )
    tasks = [{
        "task_id": "task-1",
        "overview": {"pdf_url": "https://x/overview.pdf"},
        "participants": [{"pdf_url": "https://x/paper-1.pdf"}],
    }]

    assert download_papers.process_documents(tasks, logging.getLogger("test"), workers=2) == []
    assert sorted(calls) == [
        ("task-1", "overview", "https://x/overview.pdf"),
        ("task-1", "participant", "https://x/paper-1.pdf"),
    ]


def test_failed_required_pdf_demotes_task_and_records_failure(tmp_path, monkeypatch):
    candidates_path = tmp_path / "all_candidates.jsonl"
    failures_path = tmp_path / "download_failures.jsonl"
    candidate = {
        "task_id": "trec2025-demo",
        "overview": {"pdf_url": "https://x/overview.pdf"},
        "participants": [{"pdf_url": "https://x/missing.pdf"}],
        "provenance": {"confidence": "high", "confidence_reasons": []},
        "screening": {"decision": "include"},
    }
    write_jsonl([candidate], candidates_path)
    previous_failure = {
        "task_id": "older-task",
        "pdf_url": "https://x/older-missing.pdf",
        "reason": "download_failed",
    }
    write_jsonl([previous_failure], failures_path)
    monkeypatch.setattr(download_papers, "CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(download_papers, "DOWNLOAD_FAILURES_PATH", failures_path)

    tasks = [candidate]
    failed_task_ids = download_papers.demote_failed_tasks(
        tasks, ["https://x/missing.pdf"], logging.getLogger("test")
    )

    assert failed_task_ids == {"trec2025-demo"}
    stored_candidate = read_jsonl(candidates_path)[0]
    assert stored_candidate["provenance"]["confidence"] == "medium"
    assert "required PDF download failed: https://x/missing.pdf" in stored_candidate["provenance"]["confidence_reasons"]
    assert read_jsonl(failures_path) == [
        previous_failure,
        {
            "task_id": "trec2025-demo",
            "pdf_url": "https://x/missing.pdf",
            "reason": "download_failed",
        },
    ]
