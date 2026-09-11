import logging

from src.fetch_trec import discover_track_url, fetch_url
from src.trec_config import TREC_EDITIONS


LOGGER = logging.getLogger("test_fetch_trec")


class Response:
    status_code = 200
    text = '<a href="./xref.html">Indexed by Track</a>'


def test_fetch_url_writes_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_trec.requests.get", fake_get)
    destination = tmp_path / "proceedings.html"

    assert fetch_url("https://example.org/proceedings", destination, LOGGER) == "fetched"
    assert fetch_url("https://example.org/proceedings", destination, LOGGER) == "cached"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert len(calls) == 1


def test_discover_track_url_from_nist_proceedings_page():
    assert discover_track_url(
        '<a href="./index.html">Proceedings</a><a href="./xref.html">By Track</a>',
        "https://trec.nist.gov/pubs/trec34/index.html",
    ) == "https://trec.nist.gov/pubs/trec34/xref.html"


def test_config_has_expected_nist_year_range():
    assert TREC_EDITIONS[0]["year"] == 2025
    assert TREC_EDITIONS[-1]["year"] == 1992
