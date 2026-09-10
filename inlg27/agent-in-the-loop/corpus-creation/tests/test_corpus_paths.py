from src.corpus_paths import (
    document_figures_dir,
    document_markdown_path,
    document_pdf_path,
    document_tables_dir,
    paper_id_for,
)


def test_document_paths_keep_all_assets_together():
    url = "https://ceur-ws.org/Vol-3497/paper-053.pdf"
    assert paper_id_for(url) == "paper-053"
    assert document_pdf_path("task", "overview", "").as_posix().endswith("task/overview/overview.pdf")
    assert document_markdown_path("task", "participant", url).as_posix().endswith("task/papers/paper-053/paper.txt.md")
    assert document_figures_dir("task", "participant", url).name == "figures"
    assert document_tables_dir("task", "participant", url).name == "tables"


def test_urls_without_a_filename_get_a_safe_fallback_id():
    assert paper_id_for("https://example.test/") == "paper"
