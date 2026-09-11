"""Official NIST TREC proceedings editions used by the source collector.

The NIST archive contains completed proceedings for TREC 1--34 (1992--2025).
The proceedings index does not yet list the 2025 volume, so that edition is
kept explicitly alongside the editions discovered from the index.
"""

from __future__ import annotations


TREC_EDITIONS = [
    {"parent_venue": "TREC", "year": 2025, "edition": 34, "collection_id": "trec2025", "proceedings_url": "https://trec.nist.gov/pubs/trec34/index.html"},
    {"parent_venue": "TREC", "year": 2024, "edition": 33, "collection_id": "trec2024", "proceedings_url": "https://trec.nist.gov/pubs/trec33/index.html"},
    {"parent_venue": "TREC", "year": 2023, "edition": 32, "collection_id": "trec2023", "proceedings_url": "https://trec.nist.gov/pubs/trec32/index.html"},
    {"parent_venue": "TREC", "year": 2022, "edition": 31, "collection_id": "trec2022", "proceedings_url": "https://trec.nist.gov/pubs/trec31/index.html"},
    {"parent_venue": "TREC", "year": 2021, "edition": 30, "collection_id": "trec2021", "proceedings_url": "https://trec.nist.gov/pubs/trec30/trec2021.html"},
    {"parent_venue": "TREC", "year": 2020, "edition": 29, "collection_id": "trec2020", "proceedings_url": "https://trec.nist.gov/pubs/trec29/trec2020.html"},
    {"parent_venue": "TREC", "year": 2019, "edition": 28, "collection_id": "trec2019", "proceedings_url": "https://trec.nist.gov/pubs/trec28/trec2019.html"},
    {"parent_venue": "TREC", "year": 2018, "edition": 27, "collection_id": "trec2018", "proceedings_url": "https://trec.nist.gov/pubs/trec27/trec2018.html"},
    {"parent_venue": "TREC", "year": 2017, "edition": 26, "collection_id": "trec2017", "proceedings_url": "https://trec.nist.gov/pubs/trec26/trec2017.html"},
    {"parent_venue": "TREC", "year": 2016, "edition": 25, "collection_id": "trec2016", "proceedings_url": "https://trec.nist.gov/pubs/trec25/trec2016.html"},
    {"parent_venue": "TREC", "year": 2015, "edition": 24, "collection_id": "trec2015", "proceedings_url": "https://trec.nist.gov/pubs/trec24/trec2015.html"},
    {"parent_venue": "TREC", "year": 2014, "edition": 23, "collection_id": "trec2014", "proceedings_url": "https://trec.nist.gov/pubs/trec23/trec2014.html"},
    {"parent_venue": "TREC", "year": 2013, "edition": 22, "collection_id": "trec2013", "proceedings_url": "https://trec.nist.gov/pubs/trec22/trec2013.html"},
    {"parent_venue": "TREC", "year": 2012, "edition": 21, "collection_id": "trec2012", "proceedings_url": "https://trec.nist.gov/pubs/trec21/t21.proceedings.html"},
    {"parent_venue": "TREC", "year": 2011, "edition": 20, "collection_id": "trec2011", "proceedings_url": "https://trec.nist.gov/pubs/trec20/t20.proceedings.html"},
    {"parent_venue": "TREC", "year": 2010, "edition": 19, "collection_id": "trec2010", "proceedings_url": "https://trec.nist.gov/pubs/trec19/t19.proceedings.html"},
    {"parent_venue": "TREC", "year": 2009, "edition": 18, "collection_id": "trec2009", "proceedings_url": "https://trec.nist.gov/pubs/trec18/t18_proceedings.html"},
    {"parent_venue": "TREC", "year": 2008, "edition": 17, "collection_id": "trec2008", "proceedings_url": "https://trec.nist.gov/pubs/trec17/t17_proceedings.html"},
    {"parent_venue": "TREC", "year": 2007, "edition": 16, "collection_id": "trec2007", "proceedings_url": "https://trec.nist.gov/pubs/trec16/t16_proceedings.html"},
    {"parent_venue": "TREC", "year": 2006, "edition": 15, "collection_id": "trec2006", "proceedings_url": "https://trec.nist.gov/pubs/trec15/t15_proceedings.html"},
    {"parent_venue": "TREC", "year": 2005, "edition": 14, "collection_id": "trec2005", "proceedings_url": "https://trec.nist.gov/pubs/trec14/t14_proceedings.html"},
    {"parent_venue": "TREC", "year": 2004, "edition": 13, "collection_id": "trec2004", "proceedings_url": "https://trec.nist.gov/pubs/trec13/t13_proceedings.html"},
    {"parent_venue": "TREC", "year": 2003, "edition": 12, "collection_id": "trec2003", "proceedings_url": "https://trec.nist.gov/pubs/trec12/t12_proceedings.html"},
    {"parent_venue": "TREC", "year": 2002, "edition": 11, "collection_id": "trec2002", "proceedings_url": "https://trec.nist.gov/pubs/trec11/t11_proceedings.html"},
    {"parent_venue": "TREC", "year": 2001, "edition": 10, "collection_id": "trec2001", "proceedings_url": "https://trec.nist.gov/pubs/trec10/t10_proceedings.html"},
    {"parent_venue": "TREC", "year": 2000, "edition": 9, "collection_id": "trec2000", "proceedings_url": "https://trec.nist.gov/pubs/trec9/t9_proceedings.html"},
    {"parent_venue": "TREC", "year": 1999, "edition": 8, "collection_id": "trec1999", "proceedings_url": "https://trec.nist.gov/pubs/trec8/t8_proceedings.html"},
    {"parent_venue": "TREC", "year": 1998, "edition": 7, "collection_id": "trec1998", "proceedings_url": "https://trec.nist.gov/pubs/trec7/t7_proceedings.html"},
    {"parent_venue": "TREC", "year": 1997, "edition": 6, "collection_id": "trec1997", "proceedings_url": "https://trec.nist.gov/pubs/trec6/t6_proceedings.html"},
    {"parent_venue": "TREC", "year": 1996, "edition": 5, "collection_id": "trec1996", "proceedings_url": "https://trec.nist.gov/pubs/trec5/t5_proceedings.html"},
    {"parent_venue": "TREC", "year": 1995, "edition": 4, "collection_id": "trec1995", "proceedings_url": "https://trec.nist.gov/pubs/trec4/t4_proceedings.html"},
    {"parent_venue": "TREC", "year": 1994, "edition": 3, "collection_id": "trec1994", "proceedings_url": "https://trec.nist.gov/pubs/trec3/t3_proceedings.html"},
    {"parent_venue": "TREC", "year": 1993, "edition": 2, "collection_id": "trec1993", "proceedings_url": "https://trec.nist.gov/pubs/trec2/t2_proceedings.html"},
    {"parent_venue": "TREC", "year": 1992, "edition": 1, "collection_id": "trec1992", "proceedings_url": "https://trec.nist.gov/pubs/trec1/t1_proceedings.html"},
]


def selected_editions(year: int | None = None) -> list[dict]:
    """Return all configured editions or the selected year."""
    if year is None:
        return list(TREC_EDITIONS)
    return [edition for edition in TREC_EDITIONS if edition["year"] == year]
