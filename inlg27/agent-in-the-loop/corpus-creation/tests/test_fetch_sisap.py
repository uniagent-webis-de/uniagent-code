import logging

from src.fetch_sisap import _fetch_sources, fetch_url


LOGGER = logging.getLogger("test_fetch_sisap")


class Response:
    status_code = 200
    text = "<html><body>SISAP</body></html>"

    def raise_for_status(self):
        return None


def test_fetch_url_writes_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_sisap.requests.get", fake_get)
    destination = tmp_path / "official.html"

    assert fetch_url("https://example.org/sisap", destination, LOGGER) == "fetched"
    assert fetch_url("https://example.org/sisap", destination, LOGGER) == "cached"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert len(calls) == 1


def test_fetch_sources_caches_github_discussion_as_json(tmp_path, monkeypatch):
    import src.fetch_sisap as fetcher

    monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetcher, "time", type("Clock", (), {"sleep": staticmethod(lambda _: None)}))
    monkeypatch.setattr(fetcher.requests, "get", lambda url, timeout, headers: Response())
    edition = {
        "collection_id": "sisap2024",
        "github_files": {
            "results_discussion": "https://api.github.com/repos/example/discussions/8",
        },
    }

    statuses = _fetch_sources(edition, LOGGER, force=False)

    assert statuses[0]["filename"] == "github_results_discussion.json"
    assert (tmp_path / "editions" / "sisap2024" / "github_results_discussion.json").exists()
