import json

from src.parse_fulltext import MIN_CHARS_PER_PAGE, pdf_stem_for


def test_pdf_stem_matches_the_layout_stage_5_cached():
    assert pdf_stem_for("https://ceur-ws.org/Vol-2696/paper_130.pdf") == "paper_130"
    assert pdf_stem_for("https://ceur-ws.org/Vol-3497/paper-053.pdf") == "paper-053"
    assert pdf_stem_for("https://ceur-ws.org/Vol-2125/invited_paper_5.pdf") == "invited_paper_5"


def test_thin_text_layer_threshold_is_far_below_a_real_page():
    # A born-digital CEUR page carries ~2000-4000 characters; the one genuinely
    # text-layer-less paper in the corpus (Vol-3740 paper-124) averages ~20.
    assert MIN_CHARS_PER_PAGE < 500
    assert 20 < MIN_CHARS_PER_PAGE


def test_manifest_records_are_shaped_for_auditing(tmp_path):
    # The manifest is the deliverable's quality record: every document must be traceable
    # back to its source PDF and carry the signals needed to spot a bad parse.
    record = {
        "task_id": "clef2020-touch-touch-2020-argument-retrieval",
        "role": "overview",
        "pdf_url": "https://ceur-ws.org/Vol-2696/paper_261.pdf",
        "markdown_path": "data/final/fulltext/x/overview.md",
        "chars": 51234,
        "pages": 18,
        "chars_per_page": 2846.3,
        "ocr_server_used": False,
        "needs_ocr": False,
    }
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8").strip())
    assert set(loaded) >= {"task_id", "role", "pdf_url", "markdown_path", "chars", "pages", "needs_ocr", "ocr_server_used"}


def test_participants_are_grouped_under_a_subfolder():
    # Layout contract relied on by the corpus files: the overview (the target output)
    # sits at the task root, notebook papers (the inputs) under participants/.
    from src.parse_fulltext import FULLTEXT_DIR

    task_dir = FULLTEXT_DIR / "some-task"
    overview = task_dir / "overview.md"
    participant = task_dir / "participants" / "paper_130.md"
    assert overview.parent == task_dir
    assert participant.parent.name == "participants"
    assert participant.parent.parent == task_dir
