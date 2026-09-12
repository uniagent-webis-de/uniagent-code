"""Official MediaEval editions and working-notes sources."""

from __future__ import annotations


# MediaEval's official history lists editions from 2010 through 2023, then 2025
# and 2026.  There is no 2024 edition.  CEUR is authoritative for the
# published proceedings where a volume exists; the official edition pages are
# still fetched for provenance and for years whose proceedings are not yet
# publicly available.
MEDIAEVAL_EDITIONS = [
    {
        "parent_venue": "MediaEval",
        "year": 2026,
        "collection_id": "mediaeval2026",
        "proceedings_url": "https://multimediaeval.github.io/editions/2026/",
        "official_url": "https://multimediaeval.github.io/editions/2026/",
        "ceur_volume": None,
        "layout": "official_only",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2025,
        "collection_id": "mediaeval2025",
        "proceedings_url": "https://multimediaeval.github.io/editions/2025/",
        "official_url": "https://multimediaeval.github.io/editions/2025/",
        "ceur_volume": None,
        "layout": "official_only",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2023,
        "collection_id": "mediaeval2023",
        "proceedings_url": "https://ceur-ws.org/Vol-3658/",
        "official_url": "https://multimediaeval.github.io/editions/2023/",
        "ceur_volume": "3658",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2022,
        "collection_id": "mediaeval2022",
        "proceedings_url": "https://ceur-ws.org/Vol-3583/",
        "official_url": "https://multimediaeval.github.io/editions/2022/",
        "ceur_volume": "3583",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2021,
        "collection_id": "mediaeval2021",
        "proceedings_url": "https://ceur-ws.org/Vol-3181/",
        "official_url": "https://multimediaeval.github.io/editions/2021/",
        "ceur_volume": "3181",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2020,
        "collection_id": "mediaeval2020",
        "proceedings_url": "https://ceur-ws.org/Vol-2882/",
        "official_url": "https://multimediaeval.github.io/editions/2020/",
        "ceur_volume": "2882",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2019,
        "collection_id": "mediaeval2019",
        "proceedings_url": "https://ceur-ws.org/Vol-2670/",
        "official_url": "https://multimediaeval.org/mediaeval2019/",
        "ceur_volume": "2670",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2018,
        "collection_id": "mediaeval2018",
        "proceedings_url": "https://ceur-ws.org/Vol-2283/",
        "official_url": "https://multimediaeval.org/mediaeval2018/",
        "ceur_volume": "2283",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2017,
        "collection_id": "mediaeval2017",
        "proceedings_url": "https://ceur-ws.org/Vol-1984/",
        "official_url": "https://multimediaeval.org/mediaeval2017/",
        "ceur_volume": "1984",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2016,
        "collection_id": "mediaeval2016",
        "proceedings_url": "https://ceur-ws.org/Vol-1739/",
        "official_url": "https://multimediaeval.org/mediaeval2016/",
        "ceur_volume": "1739",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2015,
        "collection_id": "mediaeval2015",
        "proceedings_url": "https://ceur-ws.org/Vol-1436/",
        "official_url": "https://multimediaeval.org/mediaeval2015/",
        "ceur_volume": "1436",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2014,
        "collection_id": "mediaeval2014",
        "proceedings_url": "https://ceur-ws.org/Vol-1263/",
        "official_url": "https://multimediaeval.org/mediaeval2014/",
        "ceur_volume": "1263",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2013,
        "collection_id": "mediaeval2013",
        "proceedings_url": "https://ceur-ws.org/Vol-1043/",
        "official_url": "https://multimediaeval.org/mediaeval2013/",
        "ceur_volume": "1043",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2012,
        "collection_id": "mediaeval2012",
        "proceedings_url": "https://ceur-ws.org/Vol-927/",
        "official_url": "https://multimediaeval.org/mediaeval2012/",
        "ceur_volume": "927",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2011,
        "collection_id": "mediaeval2011",
        "proceedings_url": "https://ceur-ws.org/Vol-807/",
        "official_url": "https://multimediaeval.org/mediaeval2011/",
        "ceur_volume": "807",
        "layout": "ceur_roles",
    },
    {
        "parent_venue": "MediaEval",
        "year": 2010,
        "collection_id": "mediaeval2010",
        # The legacy host currently serves the 2010 archive over HTTP; its
        # expired HTTPS certificate makes the official page unreachable.
        "proceedings_url": "http://multimediaeval.org/mediaeval2010/",
        "official_url": "http://multimediaeval.org/mediaeval2010/",
        "ceur_volume": None,
        "layout": "legacy_tasks",
    },
]


def selected_editions(year: int | None = None) -> list[dict]:
    """Return every configured edition or one selected year."""
    if year is None:
        return list(MEDIAEVAL_EDITIONS)
    return [edition for edition in MEDIAEVAL_EDITIONS if edition["year"] == year]
