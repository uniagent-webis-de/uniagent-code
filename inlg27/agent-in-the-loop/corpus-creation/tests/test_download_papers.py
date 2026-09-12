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


def test_download_pdf_retries_transient_request_failure(tmp_path, monkeypatch):
    calls = []

    def flaky_request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise download_papers.requests.Timeout("temporary timeout")
        return FakeResponse()

    monkeypatch.setattr(download_papers.requests, "get", flaky_request)
    monkeypatch.setattr(download_papers, "RETRY_DELAY_SECONDS", 0)
    destination = tmp_path / "paper.pdf"

    assert download_papers.download_pdf("https://example.test/paper.pdf", destination, logging.getLogger("test"))
    assert len(calls) == 2


def test_download_nii_pdf_uses_curl_and_writes_valid_cache(tmp_path, monkeypatch):
    class FakeProcess:
        returncode = 0
        args = []

        def __init__(self, command, **kwargs):
            option = "--output-document" if "--output-document" in command else "-o"
            output_path = command[command.index(option) + 1]
            with open(output_path, "wb") as stream:
                stream.write(FakeResponse.content)

        def communicate(self, **kwargs):
            return b"", b""

    monkeypatch.setattr(download_papers.subprocess, "Popen", FakeProcess)
    destination = tmp_path / "paper.pdf"

    assert download_papers.download_pdf(
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/paper.pdf",
        destination,
        logging.getLogger("test"),
    )
    assert download_papers.is_valid_pdf(destination)


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


def test_complete_task_is_promoted_from_staging(tmp_path, monkeypatch):
    final_dir = tmp_path / "final"
    downloads_dir = tmp_path / "downloads"
    monkeypatch.setattr(download_papers, "FINAL_DIR", final_dir)
    monkeypatch.setattr(download_papers, "DOWNLOADS_DIR", downloads_dir)
    task = {
        "task_id": "task-1",
        "overview": {"pdf_url": "https://x/overview.pdf"},
        "participants": [{"pdf_url": "https://x/paper-1.pdf"}],
    }

    workspace = download_papers.prepare_task_workspace(task, logging.getLogger("test"))
    assert workspace == downloads_dir
    assert not (final_dir / "task-1").exists()

    def fake_download(url, destination, logger):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(FakeResponse.content)
        return True

    monkeypatch.setattr(download_papers, "download_pdf", fake_download)
    assert download_papers.process_documents(
        [task], logging.getLogger("test"), workers=2, workspaces={"task-1": workspace}
    ) == []
    assert download_papers.promote_task_workspace(task, workspace, logging.getLogger("test"))
    assert download_papers.task_is_complete(task, final_dir)
    assert not (downloads_dir / "task-1").exists()


def test_incomplete_final_task_is_moved_to_staging(tmp_path, monkeypatch):
    final_dir = tmp_path / "final"
    downloads_dir = tmp_path / "downloads"
    monkeypatch.setattr(download_papers, "FINAL_DIR", final_dir)
    monkeypatch.setattr(download_papers, "DOWNLOADS_DIR", downloads_dir)
    task = {
        "task_id": "task-1",
        "overview": {"pdf_url": "https://x/overview.pdf"},
        "participants": [{"pdf_url": "https://x/paper-1.pdf"}],
    }
    overview = final_dir / "task-1" / "overview" / "overview.pdf"
    overview.parent.mkdir(parents=True)
    overview.write_bytes(FakeResponse.content)

    workspace = download_papers.prepare_task_workspace(task, logging.getLogger("test"))

    assert workspace == downloads_dir
    assert not (final_dir / "task-1").exists()
    assert (downloads_dir / "task-1" / "overview" / "overview.pdf").exists()


def test_reconcile_moves_nonaccepted_final_tasks_without_deleting_them(tmp_path, monkeypatch):
    final_dir = tmp_path / "final"
    downloads_dir = tmp_path / "downloads"
    monkeypatch.setattr(download_papers, "FINAL_DIR", final_dir)
    monkeypatch.setattr(download_papers, "DOWNLOADS_DIR", downloads_dir)
    orphan = final_dir / "task-1" / "overview" / "overview.pdf"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(FakeResponse.content)
    task = {"task_id": "task-1"}

    moved = download_papers.reconcile_final_task_dirs(
        [task], set(), logging.getLogger("test")
    )

    assert moved == {"task-1"}
    assert not (final_dir / "task-1").exists()
    assert (downloads_dir / "task-1" / "overview" / "overview.pdf").exists()


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


def test_recovered_failure_is_removed_after_successful_retry(tmp_path, monkeypatch):
    failures_path = tmp_path / "download_failures.jsonl"
    candidate = {
        "task_id": "ntcir2025-demo",
        "overview": {"pdf_url": "https://research.nii.ac.jp/overview.pdf"},
        "participants": [],
    }
    write_jsonl([{"task_id": candidate["task_id"], "pdf_url": candidate["overview"]["pdf_url"]}], failures_path)
    recovered_path = tmp_path / "overview.pdf"
    recovered_path.write_bytes(FakeResponse.content)
    monkeypatch.setattr(download_papers, "DOWNLOAD_FAILURES_PATH", failures_path)
    monkeypatch.setattr(download_papers, "document_pdf_path", lambda *args: recovered_path)

    download_papers.clear_recovered_failures([candidate], logging.getLogger("test"))

    assert read_jsonl(failures_path) == []
