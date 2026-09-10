import json
import logging
from pathlib import Path

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


def test_cached_extraction_requires_all_recorded_files(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path)
    record = {"pdffigures2_status": "ok", "pdffigures2_files": ["figures/a.png"]}
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "a.png").write_bytes(b"image")

    assert extractor.cached_extraction(record)
    (tmp_path / "figures" / "a.png").unlink()
    assert not extractor.cached_extraction(record)


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


def test_write_manifest_uses_jsonl_and_overwrites(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.jsonl"
    monkeypatch.setattr(extractor, "MANIFEST_PATH", manifest_path)
    extractor.write_manifest([{"pdf_url": "a", "pdffigures2_status": "ok"}])
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {
        "pdf_url": "a",
        "pdffigures2_status": "ok",
    }
