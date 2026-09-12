import logging

from src.fetch_mediaeval import discover_task_urls, fetch_url
from src.mediaeval_config import MEDIAEVAL_EDITIONS, selected_editions


LOGGER = logging.getLogger("test_fetch_mediaeval")


class Response:
    status_code = 200
    text = "<html><body>MediaEval</body></html>"

    def raise_for_status(self):
        return None


def test_fetch_url_writes_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return Response()

    monkeypatch.setattr("src.fetch_mediaeval.requests.get", fake_get)
    destination = tmp_path / "official.html"

    assert fetch_url("https://example.org/mediaeval", destination, LOGGER) == "fetched"
    assert fetch_url("https://example.org/mediaeval", destination, LOGGER) == "cached"
    assert destination.read_text(encoding="utf-8") == Response.text
    assert len(calls) == 1


def test_discover_task_urls_keeps_same_site_task_links_only():
    html = """
    <a href="/mediaeval2010/tasks/photo.html">Photo Task</a>
    <a href="/mediaeval2010/about/">About</a>
    <a href="https://other.example/task">External Task</a>
    <a href="papers/overview.pdf">Proceedings PDF</a>
    """
    assert discover_task_urls(html, "https://multimediaeval.org/mediaeval2010/", 2010) == [
        "https://multimediaeval.org/mediaeval2010/tasks/photo.html"
    ]


def test_config_covers_all_officially_listed_mediaeval_editions():
    assert [edition["year"] for edition in MEDIAEVAL_EDITIONS] == [
        2026, 2025, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016,
        2015, 2014, 2013, 2012, 2011, 2010,
    ]
    assert selected_editions(2010)[0]["layout"] == "legacy_tasks"
    assert selected_editions(2022)[0]["ceur_volume"] == "3583"
    assert selected_editions(2024) == []
