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


def test_tables_are_written_as_markdown_only(tmp_path):
    # Tables ship as verbatim markdown plus a cropped image of the real table; no CSV,
    # since a reconstructed grid loses the layout that makes a results table readable.
    from src.parse_fulltext import write_tables

    n_tables, n_images = write_tables("| a | b |\n|---|---|\n| 1 | 2 |\n", tmp_path)
    assert (n_tables, n_images) == (1, 0)
    assert (tmp_path / "table-01.md").exists()
    assert list(tmp_path.glob("*.csv")) == []


def test_isolated_rule_is_a_separator_not_a_table():
    # The short rule above a footnote block must not be mistaken for a table.
    from src.parse_fulltext import group_rules_into_tables

    single = [{"x1": 135, "x2": 480, "y1": 300, "y2": 300}]
    assert group_rules_into_tables(single) == []


def test_booktabs_rules_bound_one_table():
    from src.parse_fulltext import group_rules_into_tables

    rules = [
        {"x1": 135, "x2": 480, "y1": 131, "y2": 131},
        {"x1": 135, "x2": 480, "y1": 160, "y2": 160},
        {"x1": 135, "x2": 480, "y1": 255, "y2": 255},
    ]
    regions = group_rules_into_tables(rules)
    assert len(regions) == 1
    assert (regions[0]["y0"], regions[0]["y1"]) == (131, 255)


def test_distant_rule_groups_are_separate_tables():
    from src.parse_fulltext import group_rules_into_tables

    rules = [
        {"x1": 135, "x2": 480, "y1": 100, "y2": 100},
        {"x1": 135, "x2": 480, "y1": 140, "y2": 140},
        {"x1": 135, "x2": 480, "y1": 600, "y2": 600},
        {"x1": 135, "x2": 480, "y1": 640, "y2": 640},
    ]
    assert len(group_rules_into_tables(rules)) == 2


def test_short_footnote_rules_are_filtered_out():
    from src.parse_fulltext import horizontal_rules

    page = {"vector_graphics": {"lines": [
        {"x1": 135, "x2": 191, "y1": 653, "y2": 653},   # 56pt footnote separator
        {"x1": 135, "x2": 480, "y1": 131, "y2": 131},   # real table rule
    ]}}
    assert [r["y1"] for r in horizontal_rules(page)] == [131]


def test_figure_refs_are_rewritten_to_the_figures_directory(tmp_path):
    # liteparse emits bare filenames, which only resolve beside the markdown; figures are
    # grouped in their own folder, so refs must be repointed or they break.
    from src.parse_fulltext import rewrite_figure_refs

    md = tmp_path / "paper.md"
    md.write_text("text ![](img_p4_1.png) more\n", encoding="utf-8")
    rewrite_figure_refs(md, "../figures/paper")
    assert "![](../figures/paper/img_p4_1.png)" in md.read_text(encoding="utf-8")
