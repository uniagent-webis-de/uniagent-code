import json
from pathlib import Path

import pymupdf
import pytest

from src.pilot_asset_captions import export_assets


@pytest.mark.parametrize("kind,caption_y", [("Figure", 160), ("Table", 30)])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_exports_metadata_and_original_caption_pixels(tmp_path, kind, caption_y, rotation):
    """Catch missing captions in crops, incorrect page offsets, and lost image links."""
    pdf = tmp_path / "paper.pdf"
    caption = f"{kind} 1: Original caption."
    with pymupdf.open() as document:
        document.new_page(width=300, height=240)
        page = document.new_page(width=300, height=240)
        page.draw_rect((40, 80, 200, 140), fill=(0, 0, 1))
        page.insert_text((40, caption_y), caption, fontsize=10, color=(1, 0, 0))
        page.set_rotation(rotation)
        region = pymupdf.Rect(40, 80, 200, 140) * page.rotation_matrix
        caption_box = pymupdf.Rect(40, caption_y - 12, 200, caption_y + 3) * page.rotation_matrix
        document.save(pdf)
    raw = tmp_path / "raw"
    raw.mkdir()
    original = raw / "paper-Figure1-1.png"
    with pymupdf.open(pdf) as document:
        document[1].get_pixmap(clip=region).save(original)
    metadata = raw / "paper.json"
    metadata.write_text(json.dumps({"figures": [{
        "name": "1", "figType": kind, "page": 1, "caption": caption,
        "imageText": [], "renderURL": str(original), "renderDpi": 72,
        "regionBoundary": dict(zip(("x1", "y1", "x2", "y2"), region)),
        "captionBoundary": dict(zip(("x1", "y1", "x2", "y2"), caption_box)),
    }], "regionless-captions": []}))

    output = tmp_path / "pilot"
    assets, missing = export_assets(pdf, metadata, output, dpi=144)

    assert missing == []
    assert len(assets) == 1
    asset = assets[0]
    assert asset["caption"] == caption
    assert asset["page"] == 2
    assert asset["kind"] == kind.lower()
    assert asset["source_pdf_sha256"]
    assert Path(asset["source_pdf"]) == pdf
    assert (output / asset["original_image"]).resolve() == original
    image = pymupdf.Pixmap(str(output / asset["caption_image"]))
    pixels = list(zip(*[iter(image.samples)] * image.n))
    assert any(r > 180 and g < 100 and b < 100 for r, g, b in pixels)
    assert any(r < 100 and g < 100 and b > 180 for r, g, b in pixels)
    assert max(image.width, image.height) >= 320
    assert min(image.width, image.height) > 120


def test_regionless_caption_remains_explicitly_unmatched(tmp_path):
    """A detected caption without a region must never become a fabricated asset."""
    pdf = tmp_path / "paper.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(pdf)
    metadata = tmp_path / "paper.json"
    metadata.write_text(json.dumps({"figures": [], "regionless-captions": [{
        "name": "3", "figType": "Table", "page": 0,
        "text": "Table 3: Unmatched.",
        "boundary": {"x1": 10, "y1": 10, "x2": 100, "y2": 20},
    }]}))
    assets, missing = export_assets(pdf, metadata, tmp_path / "pilot", dpi=72)
    assert assets == []
    assert missing[0]["caption"] == "Table 3: Unmatched."
    assert missing[0]["page"] == 1
    assert missing[0]["reason"] == "no_asset_region"


def test_out_of_page_caption_is_rejected_instead_of_silently_clipped(tmp_path):
    """Invalid source coordinates must not produce an apparently successful image."""
    pdf = tmp_path / "paper.pdf"
    with pymupdf.open() as document:
        document.new_page(width=100, height=100)
        document.save(pdf)
    metadata = tmp_path / "paper.json"
    metadata.write_text(json.dumps({"figures": [{
        "name": "1", "figType": "Figure", "page": 0, "caption": "Figure 1.",
        "regionBoundary": {"x1": 10, "y1": 10, "x2": 80, "y2": 50},
        "captionBoundary": {"x1": 10, "y1": 90, "x2": 80, "y2": 120},
    }], "regionless-captions": []}))
    with pytest.raises(ValueError, match="outside page"):
        export_assets(pdf, metadata, tmp_path / "pilot", dpi=72)


def test_small_source_caption_overflow_is_preserved_and_flagged_for_review(tmp_path):
    """A slightly overflowing caption box must not discard the entire paper's assets."""
    pdf = tmp_path / "paper.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect((10, 10, 80, 50), fill=(0, 0, 1))
        page.insert_text((10, 96), "Figure 1", fontsize=7)
        page.get_pixmap(clip=pymupdf.Rect(10, 10, 80, 50)).save(tmp_path / "original.png")
        document.save(pdf)
    metadata = tmp_path / "paper.json"
    metadata.write_text(json.dumps({"figures": [{
        "name": "1", "figType": "Figure", "page": 0, "caption": "Figure 1",
        "regionBoundary": {"x1": 10, "y1": 10, "x2": 80, "y2": 50},
        "captionBoundary": {"x1": 10, "y1": 90, "x2": 80, "y2": 102},
        "renderURL": str(tmp_path / "original.png"), "renderDpi": 72, "imageText": [],
    }], "regionless-captions": []}))
    assets, unmatched = export_assets(pdf, metadata, tmp_path / "pilot", dpi=72)
    assert unmatched == []
    assert assets[0]["caption_boundary_clipped"] is True
    assert assets[0]["caption_bbox"] == [10, 90, 80, 102]
    assert assets[0]["crop_bbox"][3] == 100


@pytest.mark.parametrize("next_page", ["continuation", "different_columns", "new_caption", "body_text"])
def test_recovers_only_matching_uncaptioned_table_continuation(tmp_path, next_page):
    """Recover a split table, without appending unrelated tables or page prose."""
    pdf = tmp_path / "split.pdf"
    with pymupdf.open() as document:
        for index, ys in enumerate(([80, 180, 280, 370], [30, 100, 180, 260])):
            page = document.new_page(width=300, height=400)
            xs = [30, 110, 190, 270]
            if index == 1 and next_page == "different_columns":
                xs = [30, 150, 270]
            for x in xs:
                page.draw_line((x, ys[0]), (x, ys[-1]))
            for y in ys:
                page.draw_line((xs[0], y), (xs[-1], y))
            for row, y in enumerate(ys[:-1]):
                for column, x in enumerate(xs[:-1]):
                    page.insert_text((x + 4, y + 35), f"row{row} col{column}", fontsize=7)
            if index == 0:
                page.insert_text((50, 60), "Table 1: Split results", color=(1, 0, 0))
                page.insert_text((40, 110), "FIRST PAGE", fontsize=8, color=(0, 0, 1))
            else:
                page.insert_text((40, 50), "CONTINUATION", fontsize=8, color=(0, 1, 0))
                if next_page == "new_caption":
                    page.insert_text((30, 20), "Table 2: Different results", fontsize=8)
                if next_page == "body_text":
                    page.insert_text((30, 20), "A new section discusses another experiment.", fontsize=8)
        document.save(pdf)
    raw = tmp_path / "raw"
    raw.mkdir()
    original = raw / "split-Table1-1.png"
    with pymupdf.open(pdf) as document:
        document[0].get_pixmap(clip=pymupdf.Rect(30, 80, 270, 370)).save(original)
    metadata = raw / "split.json"
    metadata.write_text(json.dumps({"figures": [{
        "name": "1", "figType": "Table", "page": 0,
        "caption": "Table 1: Split results", "imageText": [],
        "renderURL": str(original), "renderDpi": 72,
        "regionBoundary": {"x1": 30, "y1": 80, "x2": 270, "y2": 370},
        "captionBoundary": {"x1": 50, "y1": 48, "x2": 190, "y2": 63},
    }], "regionless-captions": []}))

    output = tmp_path / "pilot"
    assets, missing = export_assets(pdf, metadata, output, dpi=72)
    assert missing == []
    assert len(assets) == 1
    asset = assets[0]
    expected_pages = [1, 2] if next_page == "continuation" else [1]
    assert asset["pages"] == expected_pages
    assert asset["page"] == 1
    assert asset["caption_page"] == 1
    assert [fragment["page"] for fragment in asset["fragments"]] == expected_pages
    image = pymupdf.Pixmap(str(output / asset["caption_image"]))
    pixels = list(zip(*[iter(image.samples)] * image.n))
    assert any(r > 180 and g < 100 and b < 100 for r, g, b in pixels)
    has_continuation = any(r < 100 and g > 180 and b < 100 for r, g, b in pixels)
    assert has_continuation == (next_page == "continuation")
    if next_page == "continuation":
        assert asset["continuation_review_required"] is True
        assert asset["continuation_method"] == "matching_ruled_columns"
        assert asset["fragments"][1]["asset_bbox"] == pytest.approx([30, 30, 270, 260])
