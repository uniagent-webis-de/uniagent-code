from pathlib import Path

from src.parse_sections import (
    cross_check_dblp,
    normalize_title,
    parse_ceur_volume,
    parse_dblp_titles,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_ceur_volume_extracts_sections_and_papers():
    raw_html = (FIXTURES_DIR / "ceur_vol_sample.html").read_text(encoding="utf-8")
    sections = parse_ceur_volume(raw_html, "3497")

    assert len(sections) == 2
    assert sections[0]["lab_name"] == "Large-scale biomedical semantic indexing and question answering (BioASQ)"
    assert len(sections[0]["papers"]) == 18

    first_paper = sections[0]["papers"][0]
    assert first_paper["title"] == "Overview of MedProcNER Task on Medical Procedure Detection and Entity Linking at BioASQ 2023"
    assert first_paper["authors"][0] == "Salvador Lima-López"
    assert first_paper["pdf_url"] == "https://ceur-ws.org/Vol-3497/paper-002.pdf"
    assert first_paper["position_in_section"] == 1


def test_parse_ceur_volume_normalizes_multiline_section_heading():
    raw_html = (FIXTURES_DIR / "ceur_vol_sample.html").read_text(encoding="utf-8")
    sections = parse_ceur_volume(raw_html, "3497")

    checkthat_section = sections[1]
    assert "\n" not in checkthat_section["lab_name"]
    assert checkthat_section["lab_name"].startswith("Check-Worthiness, Subjectivity")


def test_normalize_title_treats_punctuation_as_word_boundary():
    # Real-world case: DBLP spells "CheckThat!-2023", CEUR spells "CheckThat! 2023" —
    # the hyphen must not silently merge the two words into one token.
    assert normalize_title("CheckThat!-2023") == normalize_title("CheckThat! 2023")


def test_parse_dblp_titles_builds_normalized_lookup():
    raw_html = (FIXTURES_DIR / "dblp_sample.html").read_text(encoding="utf-8")
    lookup = parse_dblp_titles(raw_html)

    assert len(lookup) == 3
    key = normalize_title("Overview of MedProcNER Task on Medical Procedure Detection and Entity Linking at BioASQ 2023")
    assert lookup[key] == ["Salvador Lima-Lopez", "Eulalia Farre-Maduell", "Luis Gasco"]


def test_cross_check_dblp_matches_and_flags_unmatched(caplog):
    raw_ceur = (FIXTURES_DIR / "ceur_vol_sample.html").read_text(encoding="utf-8")
    raw_dblp = (FIXTURES_DIR / "dblp_sample.html").read_text(encoding="utf-8")
    sections = parse_ceur_volume(raw_ceur, "3497")
    dblp_lookup = parse_dblp_titles(raw_dblp)

    import logging
    logger = logging.getLogger("test")
    cross_check_dblp(sections, dblp_lookup, logger)

    all_papers = [p for s in sections for p in s["papers"]]
    matched = [p for p in all_papers if p["dblp_match"]]
    unmatched = [p for p in all_papers if not p["dblp_match"]]

    # Only the 3 papers present in the small DBLP fixture should match; the rest
    # of the 49-paper CEUR fixture is expected to be unmatched by design.
    assert len(matched) == 3
    assert len(unmatched) == len(all_papers) - 3

    # DBLP-preferred author spelling should replace the CEUR-parsed one on a match.
    checkthat_match = next(p for p in all_papers if p["title"].startswith("CSECU-DSG"))
    assert checkthat_match["dblp_match"] is True
    assert checkthat_match["authors"] == ["Abdul Aziz"]
