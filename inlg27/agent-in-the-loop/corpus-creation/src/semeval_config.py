"""Configured SemEval proceedings used by the high-precision collector."""

from __future__ import annotations


SEMEVAL_VOLUMES = [
    {
        "venue": "SemEval",
        "year": 2025,
        "collection_id": "2025.semeval-1",
        "url": "https://aclanthology.org/volumes/2025.semeval-1/",
        "provider": "acl_anthology",
    },
]


def selected_volumes(year: int | None = None) -> list[dict]:
    """Return configured SemEval proceedings, optionally restricted to one year."""
    if year is None:
        return list(SEMEVAL_VOLUMES)
    return [volume for volume in SEMEVAL_VOLUMES if volume["year"] == year]
