import json
import logging
from pathlib import Path

import pytest
from PIL import Image

from src.extract_captioned_assets import stage_publication


def test_caption_fields_survive_text_refresh_and_corpus_rebuild():
    """Independent text/build stages must not silently drop caption metadata links."""
    from src.parse_fulltext import preserve_extractor_fields
    from src.build_corpus import join_fulltext_paths

    fields = {"figures_tables_assets_path": "data/final/task/overview/figures_tables_assets.jsonl",
              "figures_tables_status": "ok", "figures_tables_review_required": True,
              "n_captioned_figures": 2, "n_captioned_tables": 3}
    refreshed = preserve_extractor_fields({"markdown_path": "paper.md"}, fields)
    assert all(refreshed.get(key) == value for key, value in fields.items())
    task = {"task_id": "task", "overview": {"pdf_url": "url"}, "participants": []}
    join_fulltext_paths(task, {("task", "url"): refreshed}, logging.getLogger("test"))
    assert all(task["overview"].get(key) == value for key, value in fields.items())


def test_stages_caption_images_and_portable_metadata_without_touching_originals(tmp_path):
    """The full runner must keep old assets and make every new image link resolve."""
    source = tmp_path / "stage"
    source.mkdir()
    for name in ("caption.png", "original.png", "part.png"):
        Image.new("RGB", (8, 8), "red").save(source / name)
    final = tmp_path / "final" / "task" / "overview"
    (final / "figures").mkdir(parents=True)
    (final / "figures" / "old.png").write_bytes(b"preserve")
    asset = {"kind": "figure", "label": "1", "page": 2, "pages": [2],
             "caption": "Figure 1: Caption", "source_pdf": str(final / "overview.pdf"),
             "caption_image": "caption.png", "original_image": "original.png",
             "fragments": [{"page": 2, "image": "part.png"}],
             "continuation_review_required": False}
    public = source / "public"
    fields = stage_publication([asset], [{"source_pdf": str(final / "overview.pdf"), "caption": "Figure 2"}], source, public, final,
                               project_root=tmp_path, status="ok", error=None)

    rows = [json.loads(line) for line in (public / "figures_tables_assets.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["caption"] == "Figure 1: Caption"
    assert rows[0]["source_pdf"] == "final/task/overview/overview.pdf"
    unmatched = json.loads((public / "figures_tables_unmatched_captions.jsonl").read_text())
    assert unmatched["source_pdf"] == "final/task/overview/overview.pdf"
    assert rows[0]["caption_image"].startswith("figures/with_captions/")
    for path in (rows[0]["caption_image"], rows[0]["original_image"], rows[0]["fragments"][0]["image"]):
        assert (public / path).is_file()
    assert (final / "figures" / "old.png").read_bytes() == b"preserve"
    assert not (final / "figures_tables_assets.jsonl").exists()
    assert fields["figures_tables_assets_path"] == "final/task/overview/figures_tables_assets.jsonl"
    assert fields["n_captioned_figures"] == 1
    assert fields["n_captioned_tables"] == 0


def test_extraction_failure_is_distinct_from_successful_empty_document(tmp_path):
    """An empty result caused by failure must not advertise zero detected tables."""
    for status in ("ok", "error"):
        public = tmp_path / status
        fields = stage_publication([], [], tmp_path, public, tmp_path / "final",
                                   project_root=tmp_path, status=status,
                                   error="extractor failed" if status == "error" else None)
        details = json.loads((public / "figures_tables_extraction.json").read_text())
        assert details["status"] == status
        assert fields["n_captioned_tables"] == (0 if status == "ok" else None)
        assert fields["figures_tables_review_required"] == (status == "error")


def test_finalize_retries_rotated_document_using_saved_extractor_metadata(tmp_path, monkeypatch):
    """Retry just the rejected document, without rerunning the corpus Java batch."""
    import pymupdf
    from src import extract_captioned_assets as runner

    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "FINAL_DIR", tmp_path / "final")
    pdf = tmp_path / "final/task/overview/overview.pdf"
    pdf.parent.mkdir(parents=True)
    work = tmp_path / "work"
    stale = work / "batch-old/raw"
    stale.mkdir(parents=True)
    (stale / "document-00000.json").write_text("stale invalid metadata")
    raw = work / "batch-0000/raw"
    raw.mkdir(parents=True)
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=240)
        page.draw_rect((40, 80, 200, 140), fill=(0, 0, 1))
        page.insert_text((40, 160), "Figure 1: Caption", color=(1, 0, 0))
        page.set_rotation(90)
        page.get_pixmap(clip=pymupdf.Rect(100, 40, 160, 200)).save(raw / "original.png")
        document.save(pdf)
    (raw / "document-00000.json").write_text(json.dumps({"figures": [{
        "name": "1", "figType": "Figure", "page": 0, "caption": "Figure 1: Caption",
        "regionBoundary": {"x1": 100, "y1": 40, "x2": 160, "y2": 200},
        "captionBoundary": {"x1": 77, "y1": 40, "x2": 92, "y2": 200},
        "renderURL": str(raw / "original.png"), "renderDpi": 72, "imageText": [],
    }], "regionless-captions": []}))
    item = {"id": "document-00000", "task_id": "task", "pdf_url": "url", "role": "overview",
            "pdf_path": "final/task/overview/overview.pdf"}
    directory = work / item["id"]
    directory.mkdir()
    (directory / "result.json").write_text(json.dumps({**item, "status": "error", "recipe": "original",
        "raw_metadata_path": str((raw / "document-00000.json").relative_to(work)),
        "error": "rotated page requires review: 1", "assets": 0, "unmatched_captions": 0,
        "missing_caption_text": 0, "continuation_pages": 0,
        "fields": {"figures_tables_review_required": True}}))

    report = runner.finalize_run([{"task_id": "task"}], [item], work, {}, dpi=72, do_publish=False)
    assert report["failed_documents"] == 0
    assert report["ok_documents"] == 1
    assert report["assets"] == 1
    result = json.loads((directory / "result.json").read_text())
    assert result["status"] == "ok"
    row = json.loads((directory / "public/figures_tables_assets.jsonl").read_text())
    assert row["page_rotation"] == 90
    assert (directory / "public" / row["caption_image"]).is_file()


def test_index_commit_rolls_back_every_index_after_midway_failure(tmp_path, monkeypatch):
    """A failed replacement must leave the original task/global indexes recoverable."""
    from src import extract_captioned_assets as runner
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_bytes(b"first original")
    second.write_bytes(b"second original")
    replace = Path.replace
    def fail_second(path, target):
        if target == second:
            raise OSError("injected index failure")
        return replace(path, target)
    monkeypatch.setattr(Path, "replace", fail_second)
    with pytest.raises(OSError, match="injected index failure"):
        runner.commit_indexes({first: b"first new", second: b"second new"}, tmp_path / "backup")
    assert first.read_bytes() == b"first original"
    assert second.read_bytes() == b"second original"


def test_new_batch_cannot_reuse_a_previous_attempts_raw_metadata(tmp_path):
    from src.extract_captioned_assets import create_batch
    first = create_batch(tmp_path, 0)
    (first / "raw").mkdir()
    (first / "raw/old.json").write_text("stale")
    second = create_batch(tmp_path, 0)
    assert second != first
    assert not (second / "raw/old.json").exists()


def test_failed_asset_copy_never_leaves_a_truncated_final_file(tmp_path, monkeypatch):
    from src import extract_captioned_assets as runner
    source, target = tmp_path / "source.png", tmp_path / "final.png"
    source.write_bytes(b"complete asset")
    def interrupted_copy(source, destination):
        Path(destination).write_bytes(b"partial")
        raise OSError("interrupted copy")
    monkeypatch.setattr(runner.shutil, "copy2", interrupted_copy)
    with pytest.raises(OSError, match="interrupted copy"):
        runner.copy_addition(source, target)
    assert not target.exists()
    assert source.read_bytes() == b"complete asset"
