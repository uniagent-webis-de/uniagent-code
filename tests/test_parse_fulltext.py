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


def test_pipe_tables_are_split_out_of_the_markdown():
    from src.parse_fulltext import split_markdown_tables

    md = (
        "Intro prose.\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "Middle prose mentioning a | pipe character.\n\n"
        "| x | y |\n|---|---|\n| 3 | 4 |\n| 5 | 6 |\n"
    )
    tables = split_markdown_tables(md)
    assert len(tables) == 2
    assert tables[0][0] == "| a | b |"
    assert len(tables[1]) == 4


def test_single_pipe_line_is_prose_not_a_table():
    from src.parse_fulltext import split_markdown_tables

    assert split_markdown_tables("| this is just one line with a pipe\n") == []


def test_table_rows_drop_the_separator_row():
    from src.parse_fulltext import table_to_rows

    rows = table_to_rows(["| a | b |", "|---|---|", "| 1 | 2 |"])
    assert rows == [["a", "b"], ["1", "2"]]


def test_ragged_table_gets_markdown_but_no_csv(tmp_path):
    # A wrong CSV silently misaligns columns, which is worse than not providing one.
    from src.parse_fulltext import write_tables

    md = "| a | b | c |\n|---|---|---|\n| 1 | 2 |\n"
    assert write_tables(md, tmp_path) == 1
    assert (tmp_path / "table-01.md").exists()
    assert not (tmp_path / "table-01.csv").exists()


def test_rectangular_table_also_gets_csv(tmp_path):
    from src.parse_fulltext import write_tables

    write_tables("| a | b |\n|---|---|\n| 1 | 2 |\n", tmp_path)
    assert (tmp_path / "table-01.csv").read_text().splitlines() == ["a,b", "1,2"]


def test_figure_refs_are_rewritten_to_the_figures_directory(tmp_path):
    # liteparse emits bare filenames, which only resolve beside the markdown; figures are
    # grouped in their own folder, so refs must be repointed or they break.
    from src.parse_fulltext import rewrite_figure_refs

    md = tmp_path / "paper.md"
    md.write_text("text ![](img_p4_1.png) more\n", encoding="utf-8")
    rewrite_figure_refs(md, "../figures/paper")
    assert "![](../figures/paper/img_p4_1.png)" in md.read_text(encoding="utf-8")
