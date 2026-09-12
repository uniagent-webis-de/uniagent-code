import logging

from src.fetch_ntcir import discover_toc_url, fetch_url
from src.ntcir_config import NTCIR_EDITIONS, selected_editions


LOGGER = logging.getLogger("test_fetch_ntcir")


class Response:
    status_code = 200
    text = '<a href="NTCIR/toc_ntcir.html">Table of Contents</a>'

    def raise_for_status(self):
        return None


def test_fetch_url_writes_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_ntcir.requests.get", fake_get)
    destination = tmp_path / "index.html"

    assert fetch_url("https://example.org/index", destination, LOGGER) == "fetched"
    assert fetch_url("https://example.org/index", destination, LOGGER) == "cached"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert len(calls) == 1


def test_fetch_url_can_refresh_cached_page(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append(url)
        response = Response()
        response.text = "fresh page"
        return response

    monkeypatch.setattr("src.fetch_ntcir.requests.get", fake_get)
    destination = tmp_path / "index.html"
    destination.write_text("old page", encoding="utf-8")

    assert fetch_url("https://example.org/index", destination, LOGGER, force=True) == "fetched"
    assert destination.read_text(encoding="utf-8") == "fresh page"
    assert calls == ["https://example.org/index"]


def test_discover_toc_url_prefers_ntcir_over_evia():
    raw = """
    <a href="../EVIA/toc_evia.html">EVIA Table of Contents</a>
    <a href="NTCIR/toc_ntcir.html">Table of Contents</a>
    """
    assert discover_toc_url(
        raw,
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/index.html",
        18,
    ) == "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/NTCIR/toc_ntcir.html"


def test_discover_toc_url_ignores_proceedings_pdf_links():
    raw = """
    <a href="proceedings.pdf">Proceedings PDF</a>
    <a href="NTCIR/toc_ntcir.html">Table of Contents</a>
    """
    assert discover_toc_url(
        raw,
        "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/index.html",
        18,
    ) == "https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings18/NTCIR/toc_ntcir.html"


def test_config_covers_completed_ntcir_editions_only():
    assert [edition["edition"] for edition in NTCIR_EDITIONS] == list(range(18, 0, -1))
    assert [edition["year"] for edition in NTCIR_EDITIONS[:3]] == [2025, 2023, 2022]
    assert selected_editions(18)[0]["collection_id"] == "ntcir18"
    assert selected_editions(19) == []
