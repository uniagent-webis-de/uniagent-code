import logging

from src.fetch_acl import fetch_volume


LOGGER = logging.getLogger("test_fetch_acl")


class Response:
    status_code = 200
    text = "<html>volume W14-17</html>"

    def raise_for_status(self):
        return None


def test_fetch_volume_writes_the_page_and_then_uses_the_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("src.fetch_acl.requests.get", lambda url, timeout, headers: calls.append(url) or Response())
    destination = tmp_path / "W14-17.html"
    assert fetch_volume("W14-17", destination, LOGGER) == "fetched"
    assert fetch_volume("W14-17", destination, LOGGER) == "cached"
    assert calls == ["https://aclanthology.org/volumes/W14-17/"]


def test_fetch_volume_rejects_a_page_for_another_volume(tmp_path, monkeypatch):
    monkeypatch.setattr("src.fetch_acl.requests.get", lambda url, timeout, headers: Response())
    assert fetch_volume("K15-2", tmp_path / "K15-2.html", LOGGER) == "failed"
    assert not (tmp_path / "K15-2.html").exists()
