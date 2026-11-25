import json
import logging
import hashlib
from pathlib import Path

import pytest

from src import extract_figs_tbls as extractor


def test_pdffigures2_command_matches_reference_jar_invocation(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    jar = tmp_path / "pdffigures2.jar"
    jar.write_bytes(b"jar")

    command = extractor.pdffigures2_command(
        pdf,
        tmp_path / "output",
        pdffigures2_dir=tmp_path,
        jar=jar,
        dpi=150,
        image_format="png",
    )

    assert command[:4] == [
        "java",
        "-Dsun.java2d.cmm=sun.java2d.cmm.kcms.KcmsServiceProvider",
        "-jar",
        str(jar.resolve()),
    ]
    assert command[-6:] == ["-i", "150", "-f", "png", "-c", "-q"]
    assert str(pdf.resolve()) in command


def test_pdffigures2_command_uses_sbt_when_no_jar(tmp_path):
    pdf = tmp_path / "paper.pdf"
    command = extractor.pdffigures2_command(
        pdf,
        tmp_path / "output",
        pdffigures2_dir=tmp_path,
        jar=None,
        dpi=200,
        image_format="jpg",
    )

    assert command[:2] == ["sbt", "-batch"]
    assert "org.allenai.pdffigures2.FigureExtractorBatchCli" in command[2]
    assert "-i 200" in command[2]
    assert "-f jpg" in command[2]


def test_pdffigures2_batch_command_uses_one_directory_run(tmp_path):
    jar = tmp_path / "pdffigures2.jar"
    command = extractor.pdffigures2_batch_command(
        tmp_path / "input",
        tmp_path / "output",
        pdffigures2_dir=tmp_path,
        jar=jar,
        dpi=150,
        image_format="png",
        threads=4,
    )

    assert command[0] == "java"
    assert str((tmp_path / "input").resolve()) in command
    assert "-e" in command
    assert command[-2:] == ["-t", "4"]


def test_classify_image_separates_figures_and_tables():
    assert extractor.classify_image(Path("paper-Figure1-1.png")) == "figures"
    assert extractor.classify_image(Path("paper-Table2-1.png")) == "tables"
    assert extractor.classify_image(Path("paper-unknown.png")) is None


def test_compatible_pdfbox_override_precedes_extractor_jar(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFFIGURES2_CLASSPATH", "/tools/pdfbox-app-2.0.37.jar")
    command = extractor.pdffigures2_command(
        tmp_path / "paper.pdf", tmp_path / "output", pdffigures2_dir=tmp_path,
        jar=tmp_path / "extractor.jar", dpi=150, image_format="png",
    )
    assert "-jar" not in command
    assert command[command.index("-cp") + 1] == "/tools/pdfbox-app-2.0.37.jar" + __import__("os").pathsep + str(tmp_path / "extractor.jar")
    assert "org.allenai.pdffigures2.FigureExtractorBatchCli" in command
    batch = extractor.pdffigures2_batch_command(
        tmp_path / "input", tmp_path / "batch", pdffigures2_dir=tmp_path,
        jar=tmp_path / "extractor.jar", dpi=150, image_format="png", threads=2,
    )
    assert batch[batch.index("-cp") + 1] == command[command.index("-cp") + 1]
    assert batch[-3:] == ["-e", "-t", "2"]


def test_cached_extraction_requires_all_recorded_files(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    record = {"pdffigures2_status": "ok", "pdffigures2_files": ["figures/a.png"]}
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "a.png").write_bytes(b"image")

    assert extractor.cached_extraction(record)
    (tmp_path / "figures" / "a.png").unlink()
    assert not extractor.cached_extraction(record)


def test_reviewed_regions_render_and_reject_source_drift(tmp_path, monkeypatch):
    pdf_engine = pytest.importorskip("pymupdf")
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    pdf = tmp_path / "paper.pdf"
    with pdf_engine.open() as document:
        page = document.new_page(width=200, height=200)
        page.draw_rect((20, 20, 100, 100), fill=(1, 0, 0))
        document.save(pdf)
    figures, tables = tmp_path / "figures", tmp_path / "tables"
    monkeypatch.setattr(extractor, "document_pdf_path", lambda *args: pdf)
    monkeypatch.setattr(extractor, "document_figures_dir", lambda *args: figures)
    monkeypatch.setattr(extractor, "document_tables_dir", lambda *args: tables)
    curation = tmp_path / "curation"
    curation.mkdir()
    entry = {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
             "regions": [{"page": 1, "kind": "figure", "label": "1",
                          "bbox_fraction": [.1, .1, .5, .5]}]}
    (curation / "figure_regions.json").write_text(json.dumps({"task|url": entry}))
    previous = {"chars": 42, "pdffigures2_status": "error", "pdffigures2_error": "scanned page"}
    record = extractor.apply_reviewed_assets("task", "overview", "url", previous,
        dpi=72, logger=logging.getLogger("test"))
    assert record["chars"] == 42
    assert record["pdffigures2_status"] == "error"
    assert record["n_figures"] == 1
    assert record["n_tables"] == 0
    image = pdf_engine.Pixmap(str(tmp_path / record["reviewed_assets"]["files"][0]))
    assert (image.width, image.height) == (80, 80)
    assert image.pixel(40, 40) == (255, 0, 0)
    assert record["reviewed_assets"]["status"] == "ok"
    assert record["task_id"] == "task"
    assert record["pdf_url"] == "url"
    (figures / "reviewed-figure-1-p1.png").unlink()
    record = extractor.apply_reviewed_assets("task", "overview", "url", record,
        dpi=72, logger=logging.getLogger("test"))
    assert (figures / "reviewed-figure-1-p1.png").is_file()
    invalid = dict(entry, regions=[dict(entry["regions"][0], bbox_fraction=[0, 0, 2, 1])])
    (curation / "figure_regions.json").write_text(json.dumps({"task|url": invalid}))
    with pytest.raises(ValueError, match="invalid reviewed region"):
        extractor.apply_reviewed_assets("task", "overview", "url", record,
            dpi=72, logger=logging.getLogger("test"))
    (curation / "figure_regions.json").write_text(json.dumps({"task|url": entry}))
    # A changed source must fail before touching previously reviewed outputs.
    saved = (figures / "reviewed-figure-1-p1.png").read_bytes()
    pdf.write_bytes(pdf.read_bytes() + b"\n% changed")
    with pytest.raises(ValueError, match="source changed"):
        extractor.apply_reviewed_assets("task", "overview", "url", record,
            dpi=72, logger=logging.getLogger("test"))
    assert (figures / "reviewed-figure-1-p1.png").read_bytes() == saved


def test_refresh_asset_counts_keeps_empty_canonical_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    figures = tmp_path / "data" / "final" / "task" / "overview" / "figures"
    tables = tmp_path / "data" / "final" / "task" / "overview" / "tables"

    record = extractor.refresh_asset_counts({"pdf_url": "paper.pdf"}, figures, tables)

    assert figures.is_dir()
    assert tables.is_dir()
    assert record["figures_dir"] == "data/final/task/overview/figures"
    assert record["tables_dir"] == "data/final/task/overview/tables"
    assert record["n_figures"] == 0
    assert record["n_tables"] == 0


def test_asset_counts_do_not_count_legacy_markdown_as_table_images(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    figures, tables = tmp_path / "figures", tmp_path / "tables"
    tables.mkdir()
    (tables / "reviewed-table-1.png").write_bytes(b"image")
    (tables / "table-01.md").write_text("| a | b |")
    record = extractor.refresh_asset_counts({}, figures, tables)
    assert record["n_tables"] == record["n_table_images"] == 1


def test_process_document_copies_and_classifies_pdffigures2_images(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    task_id = "task"
    pdf_url = "https://example.org/paper.pdf"
    pdf_path = tmp_path / "data" / "final" / task_id / "overview" / "overview.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-test")

    def fake_run(*args, **kwargs):
        output_dir = args[1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.json").write_text("{}", encoding="utf-8")
        figure = output_dir / "paper-Figure1-1.png"
        table = output_dir / "paper-Table1-1.png"
        figure.write_bytes(b"figure")
        table.write_bytes(b"table")
        return [figure, table]

    monkeypatch.setattr(extractor, "run_pdffigures2", fake_run)
    monkeypatch.setattr(extractor, "document_pdf_path", lambda *args: pdf_path)
    monkeypatch.setattr(
        extractor,
        "document_figures_dir",
        lambda *args: tmp_path / "data" / "final" / task_id / "overview" / "figures",
    )
    monkeypatch.setattr(
        extractor,
        "document_tables_dir",
        lambda *args: tmp_path / "data" / "final" / task_id / "overview" / "tables",
    )
    logger = logging.getLogger("test_extract_figs_tbls")
    record = extractor.process_document(
        task_id,
        "overview",
        pdf_url,
        {"chars": 42},
        pdffigures2_dir=tmp_path,
        jar=None,
        dpi=150,
        image_format="png",
        logger=logger,
    )

    figures = tmp_path / "data" / "final" / task_id / "overview" / "figures"
    tables = tmp_path / "data" / "final" / task_id / "overview" / "tables"
    assert (figures / "pdffigures2-paper-Figure1-1.png").read_bytes() == b"figure"
    assert (tables / "pdffigures2-paper-Table1-1.png").read_bytes() == b"table"
    assert record["chars"] == 42
    assert record["pdffigures2_status"] == "ok"
    assert record["pdffigures2_figures"] == 1
    assert record["pdffigures2_tables"] == 1
    assert len(record["pdffigures2_files"]) == 2

    # A second call must reuse the cache without deleting its images.
    def unexpected_extraction(*args, **kwargs):
        raise AssertionError("valid cache should avoid re-extraction")

    monkeypatch.setattr(extractor, "run_pdffigures2", unexpected_extraction)
    cached = extractor.process_document(
        task_id, "overview", pdf_url, record, pdffigures2_dir=tmp_path,
        jar=None, dpi=150, image_format="png", logger=logger,
    )
    assert cached["n_figures"] == 1
    assert cached["n_tables"] == 1
    assert (figures / "pdffigures2-paper-Figure1-1.png").read_bytes() == b"figure"
    assert (tables / "pdffigures2-paper-Table1-1.png").read_bytes() == b"table"


def test_write_manifest_uses_jsonl_and_overwrites(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.jsonl"
    monkeypatch.setattr(extractor, "MANIFEST_PATH", manifest_path)
    extractor.write_manifest([{"pdf_url": "a", "pdffigures2_status": "ok"}])
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {
        "pdf_url": "a",
        "pdffigures2_status": "ok",
    }
