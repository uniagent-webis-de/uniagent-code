#!/usr/bin/env python
"""Stage 1 — fetch and cache CEUR-WS volume index pages and DBLP working-notes records."""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CEUR_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ceur"
DBLP_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "dblp"
LOGS_DIR = PROJECT_ROOT / "logs"

CEUR_URL_TEMPLATE = "https://ceur-ws.org/Vol-{volume}/"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 1.0

# Parent venue | year | CEUR-WS volume | DBLP working-notes record (PLAN.md section 2)
VOLUME_MAP = [
    {"parent_venue": "CLEF", "year": 2025, "volume": "4038", "dblp_url": "https://dblp.org/db/conf/clef/clef2025w.html"},
    {"parent_venue": "CLEF", "year": 2024, "volume": "3740", "dblp_url": "https://dblp.org/db/conf/clef/clef2024w.html"},
    {"parent_venue": "CLEF", "year": 2023, "volume": "3497", "dblp_url": "https://dblp.org/db/conf/clef/clef2023w.html"},
    {"parent_venue": "CLEF", "year": 2022, "volume": "3180", "dblp_url": "https://dblp.org/db/conf/clef/clef2022w.html"},
    {"parent_venue": "CLEF", "year": 2021, "volume": "2936", "dblp_url": "https://dblp.org/db/conf/clef/clef2021w.html"},
    {"parent_venue": "CLEF", "year": 2020, "volume": "2696", "dblp_url": "https://dblp.org/db/conf/clef/clef2020w.html"},
    {"parent_venue": "CLEF", "year": 2019, "volume": "2380", "dblp_url": "https://dblp.org/db/conf/clef/clef2019w.html"},
    {"parent_venue": "CLEF", "year": 2018, "volume": "2125", "dblp_url": "https://dblp.org/db/conf/clef/clef2018w.html"},
]


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"fetch_volumes_{timestamp}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    return log_path


def fetch_url(url: str, dest_path: Path, logger: logging.Logger) -> str:
    """Fetch url to dest_path unless already cached. Returns "cached", "fetched", or "failed"."""
    if dest_path.exists():
        logger.info("cache hit: %s -> %s", url, dest_path)
        return "cached"

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "uniagent-corpus-builder/0.1"})
    except requests.RequestException as exc:
        logger.error("fetch failed: %s (%s)", url, exc)
        return "failed"

    logger.info("fetched: %s status=%d -> %s", url, response.status_code, dest_path)
    if response.status_code != 200:
        logger.warning("non-200 status for %s: %d", url, response.status_code)
        return "failed"

    dest_path.write_text(response.text, encoding="utf-8")
    return "fetched"


def fetch_all(volumes: list[dict], logger: logging.Logger) -> None:
    for entry in volumes:
        ceur_url = CEUR_URL_TEMPLATE.format(volume=entry["volume"])
        ceur_dest = CEUR_RAW_DIR / f"Vol-{entry['volume']}.html"
        ceur_status = fetch_url(ceur_url, ceur_dest, logger)
        if ceur_status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)
        if ceur_status == "failed":
            logger.warning("skipping %s %s due to CEUR fetch failure", entry["parent_venue"], entry["year"])

        dblp_dest = DBLP_RAW_DIR / f"{entry['parent_venue']}{entry['year']}.html"
        dblp_status = fetch_url(entry["dblp_url"], dblp_dest, logger)
        if dblp_status == "fetched":
            time.sleep(REQUEST_DELAY_SECONDS)
        if dblp_status == "failed":
            logger.warning(
                "DBLP cross-check source unavailable for %s %s (%s) — Stage 2 will log unmatched papers, not fail",
                entry["parent_venue"], entry["year"], entry["dblp_url"],
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache CEUR-WS volume index pages and DBLP working-notes records.")
    parser.add_argument("--volume", type=str, default=None, help="Fetch only this CEUR-WS volume number (e.g. 3497). Default: fetch all volumes in the map.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("fetch_volumes")
    logger.info("logging to %s", log_path)

    volumes = VOLUME_MAP
    if args.volume is not None:
        volumes = [entry for entry in VOLUME_MAP if entry["volume"] == args.volume]
        if not volumes:
            logger.error("volume %s not found in VOLUME_MAP", args.volume)
            sys.exit(1)

    fetch_all(volumes, logger)


if __name__ == "__main__":
    main()
