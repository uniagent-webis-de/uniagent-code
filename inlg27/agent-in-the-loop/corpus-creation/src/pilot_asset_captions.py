"""Run a one-to-three-paper caption pilot without changing the assembled corpus."""

import argparse
import hashlib
import html
import json
import logging
import math
import os
from pathlib import Path
import sys

import pymupdf
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract_figs_tbls import (
    DEFAULT_PDFFIGURES2_DIR,
    PROJECT_ROOT,
    resolve_pdffigures2,
    run_pdffigures2,
)


def table_continuations(document, page_index: int, region, figures: list[dict]) -> list[dict]:
    """Match adjacent ruled grids; leave inferred associations marked for review.

    Only near-bottom tables followed by a near-top grid with the same columns qualify.
    New captions, intervening prose, ambiguous grids, and rotated pages stop recovery.
    This intentionally does not attempt unruled tables or repeated-caption merging.
    """
    page = document[page_index]
    if region.y1 < page.rect.height * .85:
        return []
    tables = [table for table in page.find_tables(use_layout=False).tables
              if table.col_count >= 2 and all(abs(a - b) <= 3 for a, b in zip(table.bbox, region))]
    if len(tables) != 1:
        return []

    def columns(table):
        """Cluster nearly coincident cell edges into a stable column signature."""
        edges = sorted({cell[side] for cell in table.cells if cell for side in (0, 2)})
        result = []
        for edge in edges:
            if not result or edge - result[-1] > 2:
                result.append(edge)
        return result

    signature = columns(tables[0])
    column_count = tables[0].col_count
    continuations = []
    while region.y1 >= page.rect.height * .85 and page_index + 1 < len(document):
        next_page = document[page_index + 1]
        if next_page.rotation:
            break
        candidates = []
        for table in next_page.find_tables(use_layout=False).tables:
            bounds = pymupdf.Rect(table.bbox)
            edges = columns(table)
            if (bounds.y0 > next_page.rect.height * .15 or table.col_count != column_count
                    or len(edges) != len(signature)
                    or any(abs(a - b) > 3 for a, b in zip(edges, signature))):
                continue
            above = pymupdf.Rect(bounds.x0 - 3, 0, bounds.x1 + 3, bounds.y0 - 3)
            if any(any(char.isalpha() for char in word[4])
                   for word in next_page.get_text("words", clip=above)):
                continue
            if any(item["page"] == page_index + 1 and bounds.intersects(pymupdf.Rect([
                    item["regionBoundary"][key] for key in ("x1", "y1", "x2", "y2")]))
                   for item in figures):
                continue
            candidates.append((bounds, edges))
        if len(candidates) != 1:
            break
        region, edges = candidates[0]
        page_index += 1
        page = next_page
        continuations.append({"page": page_index + 1, "asset_bbox": list(region),
                              "column_boundaries": edges})
        logging.getLogger(__name__).info("Matched table continuation on PDF page %d", page_index + 1)
    return continuations


def export_assets(pdf_path: Path, metadata_path: Path, output_dir: Path, *, dpi: int):
    """Render original PDF pixels spanning each detected asset and its caption.

    Coordinates are top-left displayed-page points (72 DPI); page numbers start at 1.
    PDFFigures2 boxes and get_pixmap clips both use the displayed page orientation.
    """
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = {"source_pdf": str(pdf_path.resolve()),
              "source_pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest()}
    assets = []
    with pymupdf.open(pdf_path) as document:
        for index, figure in enumerate(metadata["figures"], start=1):
            page_index = figure["page"]
            if not isinstance(page_index, int) or not 0 <= page_index < len(document):
                raise ValueError(f"invalid page: {page_index}")
            page = document[page_index]
            boxes = []
            caption_boundary_clipped = False
            for key in ("regionBoundary", "captionBoundary"):
                box = [figure[key][name] for name in ("x1", "y1", "x2", "y2")]
                if not all(math.isfinite(value) for value in box):
                    raise ValueError(f"non-finite {key}")
                rect = pymupdf.Rect(box)
                small_caption_overflow = (key == "captionBoundary" and not rect.is_empty
                    and rect.x0 >= -3 and rect.y0 >= -3
                    and rect.x1 <= page.rect.width + 3 and rect.y1 <= page.rect.height + 3)
                if rect.is_empty or (not page.rect.contains(rect) and not small_caption_overflow):
                    raise ValueError(f"{key} empty or outside page {page_index + 1}: {box}")
                if not page.rect.contains(rect):
                    caption_boundary_clipped = True
                boxes.append(rect)
            if not figure["caption"].strip():
                raise ValueError(f"empty caption for asset {index}")
            kind = figure["figType"].lower()
            if kind not in ("figure", "table"):
                raise ValueError(f"unsupported asset kind: {kind}")
            original = Path(figure["renderURL"])
            if not original.is_absolute():
                original = metadata_path.parent / original
            if not original.is_file():
                raise FileNotFoundError(f"missing original crop: {original}")
            bounds = boxes[0] | boxes[1]
            crop = pymupdf.Rect(bounds.x0 - 3, bounds.y0 - 3,
                                bounds.x1 + 3, bounds.y1 + 3) & page.rect
            output_dir.mkdir(parents=True, exist_ok=True)
            image = output_dir / f"{index:03d}-{kind}-with-caption.png"
            continuations = (table_continuations(document, page_index, boxes[0], metadata["figures"])
                             if kind == "table" and not page.rotation else [])
            fragments = [{"page": page_index + 1, "asset_bbox": list(boxes[0]),
                          "crop_bbox": list(crop)}]
            for continuation in continuations:
                bounds = pymupdf.Rect(continuation["asset_bbox"])
                continuation_page = document[continuation["page"] - 1]
                padded = pymupdf.Rect(bounds.x0 - 3, bounds.y0 - 3,
                                     bounds.x1 + 3, bounds.y1 + 3) & continuation_page.rect
                fragments.append({**continuation, "crop_bbox": list(padded)})
            parts = []
            for fragment in fragments:
                pixmap = document[fragment["page"] - 1].get_pixmap(
                    clip=pymupdf.Rect(fragment["crop_bbox"]), dpi=dpi, alpha=False)
                path = (image if not continuations else
                        output_dir / f"{index:03d}-{kind}-page-{fragment['page']}.png")
                pixmap.save(path)
                fragment["image"] = path.name
                if continuations:
                    parts.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
            if continuations:
                # A visible gap separates original page fragments; no source text is synthesized.
                combined = Image.new("RGB", (max(part.width for part in parts),
                                              sum(part.height for part in parts) + 12 * (len(parts) - 1)), "white")
                top = 0
                for part in parts:
                    combined.paste(part, (0, top))
                    top += part.height + 12
                combined.save(image)
            assets.append({
                **source, "kind": kind, "label": figure["name"],
                "page": page_index + 1, "caption": figure["caption"],
                "asset_bbox": list(boxes[0]), "caption_bbox": list(boxes[1]),
                "crop_bbox": list(crop), "coordinate_system": "top-left PDF points (72 DPI)",
                "dpi": dpi, "original_image": os.path.relpath(original, output_dir),
                "caption_image": image.name, "caption_page": page_index + 1,
                "page_rotation": page.rotation,
                "caption_boundary_clipped": caption_boundary_clipped,
                "pages": [fragment["page"] for fragment in fragments], "fragments": fragments,
                "continuation_method": "matching_ruled_columns" if continuations else None,
                "continuation_review_required": bool(continuations),
            })
    unmatched = [{**source, "kind": item["figType"].lower(), "label": item["name"],
                  "page": item["page"] + 1, "caption": item["text"],
                  "caption_bbox": item["boundary"], "reason": "no_asset_region"}
                 for item in metadata.get("regionless-captions", [])]
    return assets, unmatched


def write_gallery(root: Path, assets: list[dict], unmatched: list[dict]) -> None:
    """Write a local comparison gallery with original crops and source captions."""
    escape = html.escape
    sections = []
    for asset in assets:
        source_link = os.path.relpath(asset["source_pdf"], root)
        pages = ", ".join(str(page) for page in asset["pages"])
        continuation_note = ('<p><strong>Continuation recovered by matching ruled columns; '
                             'review the page association against the source PDF.</strong></p>'
                             if asset["continuation_review_required"] else "")
        sections.append(
            f'<section><h2>{escape(asset["document_id"])} — {asset["kind"]} '
            f'{escape(asset["label"])} · PDF pages {pages}</h2>'
            f'<p>{escape(asset["caption"])}</p>'
            f'{continuation_note}'
            f'<p><a href="{escape(source_link, quote=True)}#page={asset["page"]}">Source PDF</a></p>'
            '<div class="pair"><figure><figcaption>Original crop</figcaption>'
            f'<img src="{escape(asset["original_image"], quote=True)}"></figure>'
            '<figure><figcaption>Crop including original caption</figcaption>'
            f'<img src="{escape(asset["caption_image"], quote=True)}"></figure></div></section>'
        )
    missing = "".join(f'<li>{escape(item["document_id"])} · page {item["page"]}: '
                      f'{escape(item["caption"])}</li>' for item in unmatched)
    (root / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Caption extraction pilot</title><style>'
        'body{font:16px system-ui;margin:32px auto;max-width:1500px;padding:0 20px}'
        '.pair{display:flex;gap:24px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:280px}'
        'img{max-width:100%;height:auto;border:1px solid #bbb}section{padding:24px 0;border-top:1px solid #bbb}'
        'figcaption{margin:12px 0}p{max-width:1000px}</style>'
        f'<h1>Caption extraction pilot</h1><p>{len(assets)} exported assets; '
        f'{len(unmatched)} captions without a detected asset region. Pages start at 1. '
        'Caption text and crop associations require source review.</p>'
        + "".join(sections) + f'<h2>Unmatched captions</h2><ul>{missing}</ul></html>',
        encoding="utf-8",
    )


def run_pilot(pdfs: list[Path], root: Path, *, checkout: Path, jar: Path | None, dpi: int) -> dict:
    """Keep raw outputs, derivative images, and JSONL metadata in a fresh directory."""
    root = root.resolve()
    if root.is_relative_to((PROJECT_ROOT / "data" / "final").resolve()):
        raise ValueError("pilot output must be outside data/final")
    # Snapshot each source directory, including ignored images and metadata.
    source_files = {path for pdf in pdfs for path in pdf.parent.rglob("*") if path.is_file()}
    manifest = PROJECT_ROOT / "data" / "final" / "manifest.jsonl"
    if manifest.is_file():
        source_files.add(manifest)
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_files)}
    root.mkdir(parents=True, exist_ok=False)
    (root / "source-checksums.json").write_text(json.dumps(before, indent=2) + "\n")
    logger = logging.getLogger(__name__)
    assets, unmatched, documents = [], [], []
    for index, pdf in enumerate(pdfs, start=1):
        document_id = f"document-{index:02d}"
        directory = root / document_id
        raw = directory / "raw"
        run_pdffigures2(pdf, raw, pdffigures2_dir=checkout, jar=jar, dpi=dpi,
                       image_format="png", logger=logger)
        metadata = raw / f"{pdf.stem}.json"
        exported, missing = export_assets(pdf, metadata, directory, dpi=dpi)
        for item in exported:
            for key in ("original_image", "caption_image"):
                item[key] = str(Path(document_id) / item[key])
            for fragment in item["fragments"]:
                fragment["image"] = str(Path(document_id) / fragment["image"])
        for item in exported + missing:
            item["document_id"] = document_id
        assets.extend(exported)
        unmatched.extend(missing)
        documents.append({"document_id": document_id, "source_pdf": str(pdf),
                          "assets": len(exported), "unmatched_captions": len(missing)})
        logger.info("%s: %d assets; %d unmatched captions", pdf, len(exported), len(missing))
    for filename, records in (("figures_tables_assets.jsonl", assets), ("unmatched-captions.jsonl", unmatched)):
        (root / filename).write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
                                     encoding="utf-8")
    write_gallery(root, assets, unmatched)
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_files)}
    if before != after:
        raise RuntimeError("source preservation check failed")
    summary = {"documents": documents, "assets": len(assets),
               "figures": sum(item["kind"] == "figure" for item in assets),
               "tables": sum(item["kind"] == "table" for item in assets),
               "multi_page_tables": sum(len(item["pages"]) > 1 for item in assets),
               "continuation_pages": sum(len(item["pages"]) - 1 for item in assets),
               "unmatched_captions": len(unmatched), "dpi": dpi,
               "source_files_verified_unchanged": len(before),
               "extractor": "allenai/pdffigures2", "renderer": f"pymupdf {pymupdf.VersionBind}",
               "visual_review": "pending"}
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    """Run a deliberately capped pilot; never launch a corpus-wide extraction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", type=Path, nargs="+", help="One to three local source PDFs.")
    parser.add_argument("--output-dir", type=Path, required=True, help="A new directory outside data/final.")
    parser.add_argument("--pdffigures2-dir", type=Path, default=DEFAULT_PDFFIGURES2_DIR)
    parser.add_argument("--pdffigures2-jar", type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()
    if len(args.pdfs) > 3 or args.dpi <= 0:
        parser.error("pilot accepts at most three PDFs and a positive DPI")
    pdfs = [pdf.expanduser().resolve(strict=True) for pdf in args.pdfs]
    logs = PROJECT_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logs / "pilot_asset_captions.log", filemode="w",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        checkout, jar = resolve_pdffigures2(args.pdffigures2_dir, args.pdffigures2_jar)
        summary = run_pilot(pdfs, args.output_dir, checkout=checkout, jar=jar, dpi=args.dpi)
        logging.info("Pilot finished: %s", summary)
    except Exception:
        logging.exception("Caption pilot failed")
        raise


if __name__ == "__main__":
    main()
