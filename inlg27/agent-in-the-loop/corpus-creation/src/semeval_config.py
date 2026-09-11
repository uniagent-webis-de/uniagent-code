"""Configured SemEval proceedings used by the high-precision collector.

The ACL Anthology uses modern ``YYYY.semeval-1`` identifiers from 2020 onward and
legacy ``Sxx-*`` identifiers for earlier proceedings.  SENSEVAL (1998, 2001, 2004)
is the predecessor venue, not a SemEval edition, and is intentionally not included.
"""

from __future__ import annotations


SEMEVAL_VOLUMES = [
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2026,
        "collection_id": "2026.semeval-1",
        "url": "https://aclanthology.org/volumes/2026.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2025,
        "collection_id": "2025.semeval-1",
        "url": "https://aclanthology.org/volumes/2025.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2024,
        "collection_id": "2024.semeval-1",
        "url": "https://aclanthology.org/volumes/2024.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2023,
        "collection_id": "2023.semeval-1",
        "url": "https://aclanthology.org/volumes/2023.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2022,
        "collection_id": "2022.semeval-1",
        "url": "https://aclanthology.org/volumes/2022.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2021,
        "collection_id": "2021.semeval-1",
        "url": "https://aclanthology.org/volumes/2021.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2020,
        "collection_id": "2020.semeval-1",
        "url": "https://aclanthology.org/volumes/2020.semeval-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2019,
        "collection_id": "S19-2",
        "url": "https://aclanthology.org/volumes/S19-2/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2018,
        "collection_id": "S18-1",
        "url": "https://aclanthology.org/volumes/S18-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2017,
        "collection_id": "S17-2",
        "url": "https://aclanthology.org/volumes/S17-2/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2016,
        "collection_id": "S16-1",
        "url": "https://aclanthology.org/volumes/S16-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2015,
        "collection_id": "S15-2",
        "url": "https://aclanthology.org/volumes/S15-2/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2014,
        "collection_id": "S14-2",
        "url": "https://aclanthology.org/volumes/S14-2/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2013,
        "collection_id": "S13-2",
        "url": "https://aclanthology.org/volumes/S13-2/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2012,
        "collection_id": "S12-1",
        "url": "https://aclanthology.org/volumes/S12-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2010,
        "collection_id": "S10-1",
        "url": "https://aclanthology.org/volumes/S10-1/",
        "provider": "acl_anthology",
    },
    {
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2007,
        "collection_id": "S07-1",
        "url": "https://aclanthology.org/volumes/S07-1/",
        "provider": "acl_anthology",
    },
]


def selected_volumes(year: int | None = None) -> list[dict]:
    """Return configured SemEval proceedings, optionally restricted to one year."""
    if year is None:
        return list(SEMEVAL_VOLUMES)
    return [volume for volume in SEMEVAL_VOLUMES if volume["year"] == year]
