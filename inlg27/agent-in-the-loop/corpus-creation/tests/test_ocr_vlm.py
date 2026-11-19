import json
import logging

from src.ocr_vlm import html_tables_to_markdown, ocr_document

LOG = logging.getLogger("t")


def test_html_table_becomes_compact_markdown_and_keeps_odd_cells():
    text = "Before\n<table><thead><tr><th>Topic</th><th>Ratio</th></tr></thead><tbody>" \
           "<tr><td>T1</td><td>0.59</td></tr><tr><td>F07</td><td>==</td></tr></tbody></table>\nAfter"
    out = html_tables_to_markdown(text)
    assert "<table" not in out and "Before" in out and "After" in out
    assert "| Topic | Ratio |" in out and "|---|---|" in out
    assert "| F07 | == |" in out  # odd cells are transcribed, not "fixed"


def test_table_rows_are_padded_and_pipes_escaped():
    out = html_tables_to_markdown("<table><tr><td>a|b</td><td>c</td></tr><tr><td>only</td></tr></table>")
    assert "a\\|b" in out and "| only |  |" in out


def test_ocr_document_resumes_from_cache_and_reports_truncated_pages(tmp_path):
    calls = []

    def recognize(index):
        calls.append(index)
        return f"page {index}", index == 1  # page 2 (index 1) hit the token cap

    cache = tmp_path / "c.json"
    text, truncated = ocr_document(3, recognize, cache, LOG)
    assert truncated == [2] and text.count("page") == 3 and calls == [0, 1, 2]

    calls.clear()  # a second run must not redo finished pages
    text2, truncated2 = ocr_document(3, recognize, cache, LOG)
    assert calls == [] and text2 == text and truncated2 == [2]

    cache.write_text(json.dumps({"0": {"text": "kept", "truncated": False}}))  # interrupted after page 1
    ocr_document(3, recognize, cache, LOG)
    assert calls == [1, 2]
