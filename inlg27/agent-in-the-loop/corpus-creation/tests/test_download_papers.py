import logging

from src import download_papers
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
