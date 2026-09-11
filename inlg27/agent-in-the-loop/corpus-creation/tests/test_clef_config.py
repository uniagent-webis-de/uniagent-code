from src.clef_config import CLEF_VOLUMES
from src.fetch_volumes import VOLUME_MAP as FETCH_VOLUME_MAP
from src.parse_sections import VOLUME_MAP as PARSE_VOLUME_MAP


def test_config_covers_every_clef_working_notes_edition_from_2000_to_2025():
    assert [entry["year"] for entry in CLEF_VOLUMES] == list(range(2025, 1999, -1))
    assert len({entry["volume"] for entry in CLEF_VOLUMES}) == 26
    assert all(entry["parent_venue"] == "CLEF" for entry in CLEF_VOLUMES)


def test_fetch_and_parse_share_the_same_clef_volume_map():
    assert FETCH_VOLUME_MAP is CLEF_VOLUMES
    assert PARSE_VOLUME_MAP is CLEF_VOLUMES

