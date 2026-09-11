"""Official CLEF Working Notes editions and their source records.

The CLEF Initiative lists one CEUR-WS Working Notes volume for every edition
from 2000 through 2025.  Keep the map in one module so fetching and parsing
cannot silently operate on different year ranges.
"""

from __future__ import annotations


CLEF_VOLUMES = [
    {"parent_venue": "CLEF", "year": 2025, "volume": "4038", "dblp_url": "https://dblp.org/db/conf/clef/clef2025w.html"},
    {"parent_venue": "CLEF", "year": 2024, "volume": "3740", "dblp_url": "https://dblp.org/db/conf/clef/clef2024w.html"},
    {"parent_venue": "CLEF", "year": 2023, "volume": "3497", "dblp_url": "https://dblp.org/db/conf/clef/clef2023w.html"},
    {"parent_venue": "CLEF", "year": 2022, "volume": "3180", "dblp_url": "https://dblp.org/db/conf/clef/clef2022w.html"},
    {"parent_venue": "CLEF", "year": 2021, "volume": "2936", "dblp_url": "https://dblp.org/db/conf/clef/clef2021w.html"},
    {"parent_venue": "CLEF", "year": 2020, "volume": "2696", "dblp_url": "https://dblp.org/db/conf/clef/clef2020w.html"},
    {"parent_venue": "CLEF", "year": 2019, "volume": "2380", "dblp_url": "https://dblp.org/db/conf/clef/clef2019w.html"},
    {"parent_venue": "CLEF", "year": 2018, "volume": "2125", "dblp_url": "https://dblp.org/db/conf/clef/clef2018w.html"},
    {"parent_venue": "CLEF", "year": 2017, "volume": "1866", "dblp_url": "https://dblp.org/db/conf/clef/clef2017w.html"},
    {"parent_venue": "CLEF", "year": 2016, "volume": "1609", "dblp_url": "https://dblp.org/db/conf/clef/clef2016w.html"},
    {"parent_venue": "CLEF", "year": 2015, "volume": "1391", "dblp_url": "https://dblp.org/db/conf/clef/clef2015w.html"},
    {"parent_venue": "CLEF", "year": 2014, "volume": "1180", "dblp_url": "https://dblp.org/db/conf/clef/clef2014w.html"},
    {"parent_venue": "CLEF", "year": 2013, "volume": "1179", "dblp_url": "https://dblp.org/db/conf/clef/clef2013w.html"},
    {"parent_venue": "CLEF", "year": 2012, "volume": "1178", "dblp_url": "https://dblp.org/db/conf/clef/clef2012w.html"},
    {"parent_venue": "CLEF", "year": 2011, "volume": "1177", "dblp_url": "https://dblp.org/db/conf/clef/clef2011w.html"},
    {"parent_venue": "CLEF", "year": 2010, "volume": "1176", "dblp_url": "https://dblp.org/db/conf/clef/clef2010w.html"},
    {"parent_venue": "CLEF", "year": 2009, "volume": "1175", "dblp_url": "https://dblp.org/db/conf/clef/clef2009w.html"},
    {"parent_venue": "CLEF", "year": 2008, "volume": "1174", "dblp_url": "https://dblp.org/db/conf/clef/clef2008w.html"},
    {"parent_venue": "CLEF", "year": 2007, "volume": "1173", "dblp_url": "https://dblp.org/db/conf/clef/clef2007w.html"},
    {"parent_venue": "CLEF", "year": 2006, "volume": "1172", "dblp_url": "https://dblp.org/db/conf/clef/clef2006w.html"},
    {"parent_venue": "CLEF", "year": 2005, "volume": "1171", "dblp_url": "https://dblp.org/db/conf/clef/clef2005w.html"},
    {"parent_venue": "CLEF", "year": 2004, "volume": "1170", "dblp_url": "https://dblp.org/db/conf/clef/clef2004w.html"},
    {"parent_venue": "CLEF", "year": 2003, "volume": "1169", "dblp_url": "https://dblp.org/db/conf/clef/clef2003w.html"},
    {"parent_venue": "CLEF", "year": 2002, "volume": "1168", "dblp_url": "https://dblp.org/db/conf/clef/clef2002w.html"},
    {"parent_venue": "CLEF", "year": 2001, "volume": "1167", "dblp_url": "https://dblp.org/db/conf/clef/clef2001w.html"},
    {"parent_venue": "CLEF", "year": 2000, "volume": "1166", "dblp_url": "https://dblp.org/db/conf/clef/clef2000w.html"},
]


VOLUME_MAP = CLEF_VOLUMES
