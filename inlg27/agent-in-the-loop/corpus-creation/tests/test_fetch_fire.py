import logging

from src.fetch_fire import fetch_url
from src.fire_config import FIRE_EDITIONS, selected_editions


LOGGER = logging.getLogger("test_fetch_fire")


class Response:
    status_code = 200
    text = "<html><body>FIRE</body></html>"

    def raise_for_status(self):
        return None


def test_fetch_url_writes_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_fire.requests.get", fake_get)
    destination = tmp_path / "proceedings.html"

    assert fetch_url("https://example.org/proceedings", destination, LOGGER) == "fetched"
    assert fetch_url("https://example.org/proceedings", destination, LOGGER) == "cached"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert len(calls) == 1


def test_fetch_url_can_refresh_cached_page(tmp_path, monkeypatch):
    def fake_get(url, timeout, headers):
        response = Response()
        response.text = "fresh page"
        return response

    monkeypatch.setattr("src.fetch_fire.requests.get", fake_get)
    destination = tmp_path / "index.html"
    destination.write_text("old page", encoding="utf-8")

    assert fetch_url("https://example.org/index", destination, LOGGER, force=True) == "fetched"
    assert destination.read_text(encoding="utf-8") == "fresh page"


def test_config_covers_ceur_and_historical_archive_editions():
    assert FIRE_EDITIONS[0]["year"] == 2025
    assert FIRE_EDITIONS[0]["ceur_volume"] == "4173"
    assert FIRE_EDITIONS[-1]["year"] == 2008
    assert FIRE_EDITIONS[-1]["ceur_volume"] is None
    assert selected_editions(2016)[0]["collection_id"] == "fire2016"
