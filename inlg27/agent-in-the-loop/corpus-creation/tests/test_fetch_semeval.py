import logging

from src.fetch_semeval import fetch_url


LOGGER = logging.getLogger("test_fetch_semeval")


class Response:
    status_code = 200
    text = "<html>SemEval proceedings</html>"

    def raise_for_status(self):
        return None


def test_fetch_url_writes_a_source_page_and_then_uses_the_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_semeval.requests.get", fake_get)
    destination = tmp_path / "2025.semeval-1.html"

    assert fetch_url("https://example.org/semeval", destination, LOGGER) == "fetched"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert fetch_url("https://example.org/semeval", destination, LOGGER) == "cached"
    assert len(calls) == 1
