import logging

from src.fetch_semeval import fetch_url
from src.semeval_config import SEMEVAL_VOLUMES, selected_volumes


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


def test_config_covers_all_acl_semeval_editions_without_senseval():
    assert [volume["year"] for volume in SEMEVAL_VOLUMES] == [
        2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017,
        2016, 2015, 2014, 2013, 2012, 2010, 2007,
    ]
    assert all("senseval" not in volume["url"].lower() for volume in SEMEVAL_VOLUMES)
    assert selected_volumes(2013)[0]["collection_id"] == "S13-2"
    assert selected_volumes(2011) == []
