"""Stage and publish caption-aware extraction for the current indexed corpus."""

import argparse
import copy
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import PROJECT_ROOT, FINAL_DIR, document_pdf_path
from src.extract_figs_tbls import DEFAULT_PDFFIGURES2_DIR, resolve_pdffigures2, run_pdffigures2_batch
from src.pilot_asset_captions import export_assets


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    """Replace a generated JSON record atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_jsonl(path, values):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")
    temporary.replace(path)


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_batch(work, index):
    """Isolate each Java attempt so missing metadata cannot reuse a stale result."""
    return Path(tempfile.mkdtemp(prefix=f"batch-{index:04d}-", dir=work))


def copy_addition(source, target):
    """Publish a new asset atomically so an interrupted copy remains retryable."""
    if target.exists():
        if checksum(target) != checksum(source):
            raise RuntimeError(f"conflicting caption output: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".caption-tmp")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def commit_indexes(updates, backup):
    """Prepare all index replacements, restoring every original if promotion fails."""
    backup.mkdir(parents=True, exist_ok=True)
    originals = {}
    temporary = {}
    for target in updates:
        saved = backup / (hashlib.sha256(str(target).encode()).hexdigest() + ".bak")
        shutil.copy2(target, saved)
        originals[target] = saved
    write_json(backup / "paths.json", {str(target): str(saved) for target, saved in originals.items()})
    try:
        for target, content in updates.items():
            staged = target.with_name(target.name + ".caption-tmp")
            temporary[target] = staged
            staged.write_bytes(content)
        for target, staged in temporary.items():
            staged.replace(target)
    except BaseException:
        for staged in temporary.values():
            staged.unlink(missing_ok=True)
        for target, saved in originals.items():
            shutil.copy2(saved, target)
        raise
    finally:
        for staged in temporary.values():
            staged.unlink(missing_ok=True)


def stage_publication(assets, unmatched, source_dir, public, destination, *, project_root, status, error):
    """Prepare portable per-document metadata and images without changing the corpus."""
    public.mkdir(parents=True, exist_ok=True)
    rows = copy.deepcopy(assets)
    for asset in rows:
        folder = Path("figures" if asset["kind"] == "figure" else "tables") / "with_captions"
        for container, key, original in [(asset, "caption_image", False), (asset, "original_image", True)] + [
                (fragment, "image", False) for fragment in asset.get("fragments", [])]:
            source = (source_dir / container[key]).resolve()
            target = folder / ("originals" if original else "") / source.name
            (public / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, public / target)
            container[key] = target.as_posix()
        asset["source_pdf"] = str(Path(asset["source_pdf"]).relative_to(project_root))
    write_jsonl(public / "figures_tables_assets.jsonl", rows)
    portable_unmatched = copy.deepcopy(unmatched)
    for item in portable_unmatched:
        item["source_pdf"] = str(Path(item["source_pdf"]).relative_to(project_root))
    write_jsonl(public / "figures_tables_unmatched_captions.jsonl", portable_unmatched)
    review = status != "ok" or bool(unmatched) or any(
        asset.get("continuation_review_required") or asset.get("caption_boundary_clipped")
        or not asset.get("caption") for asset in rows)
    details = {"status": status, "error": error, "assets": len(rows), "unmatched_captions": len(unmatched),
               "review_required": review, "document_dir": str(destination.relative_to(project_root)),
               "continuation_pages": sum(max(0, len(asset.get("pages", [])) - 1) for asset in rows)}
    write_json(public / "figures_tables_extraction.json", details)
    return {"figures_tables_assets_path": str((destination / "figures_tables_assets.jsonl").relative_to(project_root)),
            "figures_tables_status": status, "figures_tables_review_required": review,
            "n_captioned_figures": sum(asset["kind"] == "figure" for asset in rows) if status != "error" else None,
            "n_captioned_tables": sum(asset["kind"] == "table" for asset in rows) if status != "error" else None}


def reviewed_fallback(entry, document, pdf, source_hash):
    """Preserve reviewed crops while keeping unavailable caption text explicitly unknown."""
    if entry["pdf_sha256"] != source_hash:
        raise ValueError("reviewed crop source checksum changed")
    assets = []
    for region in entry["regions"]:
        name = f"reviewed-{region['kind']}-{region['label']}-p{region['page']}.png"
        path = pdf.parent / ("figures" if region["kind"] == "figure" else "tables") / name
        if not path.is_file():
            raise FileNotFoundError(path)
        assets.append({"kind": region["kind"], "label": region["label"], "page": region["page"],
                       "pages": [region["page"]], "caption_page": region["page"], "caption": None,
                       "caption_status": "unavailable_in_reviewed_crop_metadata",
                       "caption_image": str(path), "original_image": str(path), "fragments": [],
                       "source_pdf": str(pdf), "source_pdf_sha256": source_hash,
                       "bbox_fraction": region["bbox_fraction"], "continuation_review_required": True,
                       "provenance": "source-checked curation/figure_regions.json"})
    return assets


def publish(tasks, documents, work, snapshot):
    """Promote validated additions and update only caption fields in existing indexes."""
    from src.build_corpus import validate, validate_output_files, validate_final_task_directories

    logger = logging.getLogger(__name__)
    for relative, digest in snapshot.items():
        if checksum(FINAL_DIR / relative) != digest:
            raise RuntimeError(f"source changed during extraction: {relative}")
    if not (validate(tasks, logger) and validate_output_files(tasks, logger)
            and validate_final_task_directories(tasks, logger)):
        raise RuntimeError("builder validation failed")
    ids = {task["task_id"] for task in tasks}
    for filename in ("shared_tasks.csv", "shared_tasks_summary.csv"):
        with (FINAL_DIR / filename).open() as stream:
            if {row["task_id"] for row in csv.DictReader(stream)} != ids:
                raise RuntimeError(f"CSV task IDs disagree: {filename}")
    copies = []
    for item in documents:
        public = work / item["id"] / "public"
        for asset in read_jsonl(public / "figures_tables_assets.jsonl"):
            for path in [asset["caption_image"], asset["original_image"]] + [f["image"] for f in asset["fragments"]]:
                with Image.open(public / path) as image:
                    image.verify()
        destination = PROJECT_ROOT / item["pdf_path"]
        for source in public.rglob("*"):
            if source.is_file():
                target = destination.parent / source.relative_to(public)
                if target.exists() and checksum(target) != checksum(source):
                    raise RuntimeError(f"refusing to replace an existing caption output: {target}")
                copies.append((source, target))
    logger.info("Validated staged images for all %d documents; publishing additions", len(documents))
    for source, target in copies:
        copy_addition(source, target)
    fields_by_key = {}
    for item in documents:
        result = json.loads((work / item["id"] / "result.json").read_text())
        fields_by_key[(item["task_id"], item["pdf_url"])] = result["fields"]
    updates = {}
    for task in tasks:
        for document in [task["overview"], *task["participants"]]:
            document.update(fields_by_key[(task["task_id"], document["pdf_url"])])
        metadata_path = FINAL_DIR / task["task_id"] / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        for document in [metadata["overview"], *metadata["participants"]]:
            document.update(fields_by_key[(task["task_id"], document["pdf_url"])])
        updates[metadata_path] = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode()
    manifest = read_jsonl(FINAL_DIR / "manifest.jsonl")
    for record in manifest:
        record.update(fields_by_key.get((record["task_id"], record["pdf_url"]), {}))
    updates[FINAL_DIR / "manifest.jsonl"] = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest).encode()
    updates[FINAL_DIR / "shared_tasks.jsonl"] = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in tasks).encode()
    mutable = {"manifest.jsonl", "shared_tasks.jsonl"} | {f"{task['task_id']}/metadata.json" for task in tasks}
    for relative, digest in snapshot.items():
        if relative not in mutable and checksum(FINAL_DIR / relative) != digest:
            raise RuntimeError(f"unrelated corpus file changed: {relative}")
    commit_indexes(updates, work / "publication-backup")
    logger.info("Published %d documents; all original PDFs, text, images and CSVs preserved", len(documents))


def finalize_run(tasks, documents, work, snapshot, *, dpi, do_publish):
    """Retry failed exports from saved raw metadata, then validate and publish the run."""
    logger = logging.getLogger(__name__)
    results = []
    for item in documents:
        directory = work / item["id"]
        result = json.loads((directory / "result.json").read_text())
        if result["status"] == "error":
            try:
                metadata = (work / result["raw_metadata_path"] if result.get("raw_metadata_path") else
                            next(work.glob(f"batch-*/raw/{item['id']}.json")))
                pdf = PROJECT_ROOT / item["pdf_path"]
                assets, unmatched = export_assets(pdf, metadata, directory, dpi=dpi)
                for asset in assets + unmatched:
                    asset.update(task_id=item["task_id"], pdf_url=item["pdf_url"], role=item["role"])
                fields = stage_publication(assets, unmatched, directory, directory / "public", pdf.parent,
                                           project_root=PROJECT_ROOT, status="ok", error=None)
                result.update(status="ok", error=None, fields=fields, assets=len(assets),
                              unmatched_captions=len(unmatched), missing_caption_text=0,
                              clipped_caption_assets=sum(asset.get("caption_boundary_clipped", False) for asset in assets),
                              continuation_pages=sum(len(asset["pages"]) - 1 for asset in assets),
                              recovery_renderer_sha256=checksum(PROJECT_ROOT / "src/pilot_asset_captions.py")
                              if (PROJECT_ROOT / "src/pilot_asset_captions.py").exists() else None)
                write_json(directory / "result.json", result)
                logger.info("Recovered export %s from saved raw metadata: %d assets", item["id"], len(assets))
            except Exception:
                logger.exception("Export still requires review: %s", item["id"])
        details_path = directory / "public/figures_tables_extraction.json"
        if details_path.exists():
            details = json.loads(details_path.read_text())
            if "source_pdf" in details:  # Older staged status records stored the document directory here.
                details["document_dir"] = details.pop("source_pdf")
                write_json(details_path, details)
        unmatched_path = directory / "public/figures_tables_unmatched_captions.jsonl"
        if unmatched_path.exists():
            unmatched = read_jsonl(unmatched_path)
            for entry in unmatched:
                if Path(entry["source_pdf"]).is_absolute():
                    entry["source_pdf"] = str(Path(entry["source_pdf"]).relative_to(PROJECT_ROOT))
            write_jsonl(unmatched_path, unmatched)
        results.append(result)
    report = {"tasks": len(tasks), "documents": len(documents), "assets": sum(r["assets"] for r in results),
              "figures": sum(r["fields"].get("n_captioned_figures") or 0 for r in results),
              "tables": sum(r["fields"].get("n_captioned_tables") or 0 for r in results),
              "ok_documents": sum(r["status"] == "ok" for r in results),
              "partial_documents": sum(r["status"] == "partial" for r in results),
              "failed_documents": sum(r["status"] == "error" for r in results),
              "review_documents": sum(r["fields"]["figures_tables_review_required"] for r in results),
              "continuation_pages": sum(r["continuation_pages"] for r in results),
              "missing_caption_text": sum(r["missing_caption_text"] for r in results),
              "unmatched_captions": sum(r["unmatched_captions"] for r in results),
              "clipped_caption_assets": sum(r.get("clipped_caption_assets", 0) for r in results),
              "original_files_snapshotted": len(snapshot), "published": False}
    write_jsonl(work / "failures.jsonl", [r for r in results if r["status"] != "ok"])
    write_jsonl(work / "review.jsonl", [r for r in results if r["fields"]["figures_tables_review_required"]])
    write_json(work / "report.json", report)
    if do_publish:
        publish(tasks, documents, work, snapshot)
        report["published"] = True
        write_json(work / "report.json", report)
        write_json(FINAL_DIR / "figures_tables_extraction_report.json", report)
        from src.organize_captioned_assets import organize_corpus
        organize_corpus()
    logger.info("Caption extraction finished: %s", report)
    return report


def main():
    """Batch current corpus PDFs, cache completed documents, then optionally publish."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "data/intermediate/figures-tables-full")
    parser.add_argument("--pdffigures2-jar", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--finalize", action="store_true", help="Validate a completed staged run without repeating Java extraction.")
    args = parser.parse_args()
    if min(args.threads, args.batch_size, args.dpi) <= 0:
        parser.error("threads, batch-size and dpi must be positive")
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=PROJECT_ROOT / "logs/extract_captioned_assets.log", filemode="w",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger(__name__)
    work = args.work_dir.resolve()
    if work.is_relative_to(FINAL_DIR):
        raise ValueError("work directory must be outside final corpus")
    work.mkdir(parents=True, exist_ok=True)
    checkout, jar = resolve_pdffigures2(DEFAULT_PDFFIGURES2_DIR, args.pdffigures2_jar)
    tasks = read_jsonl(FINAL_DIR / "shared_tasks.jsonl")
    documents = []
    for task in tasks:
        for role, document in [("overview", task["overview"])] + [("participant", p) for p in task["participants"]]:
            pdf = document_pdf_path(task["task_id"], role, document["pdf_url"])
            if not pdf.is_file():
                raise FileNotFoundError(pdf)
            documents.append({"id": f"document-{len(documents):05d}", "task_id": task["task_id"],
                              "role": role, "pdf_url": document["pdf_url"],
                              "pdf_path": str(pdf.relative_to(PROJECT_ROOT))})
    index_path = work / "documents.json"
    if index_path.exists() and json.loads(index_path.read_text()) != documents:
        raise RuntimeError("indexed corpus differs from this work directory")
    write_json(index_path, documents)
    snapshot_path = work / "source-checksums.json"
    if not snapshot_path.exists():
        logger.info("Snapshotting original corpus files before extraction")
        snapshot = {str(path.relative_to(FINAL_DIR)): checksum(path)
                    for path in sorted(FINAL_DIR.rglob("*")) if path.is_file()}
        write_json(snapshot_path, snapshot)
        backup = work / "index-backup"
        for name in ["shared_tasks.jsonl", "manifest.jsonl", "shared_tasks.csv", "shared_tasks_summary.csv"] + [
                f"{task['task_id']}/metadata.json" for task in tasks]:
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(FINAL_DIR / name, target)
    snapshot = json.loads(snapshot_path.read_text())
    if args.finalize:
        finalize_run(tasks, documents, work, snapshot, dpi=args.dpi, do_publish=args.publish)
        return
    recipe = hashlib.sha256((Path(__file__).read_bytes() +
                           (PROJECT_ROOT / "src/pilot_asset_captions.py").read_bytes() +
                           str(args.dpi).encode() + checksum(jar).encode())).hexdigest()
    reviewed_path = PROJECT_ROOT / "curation/figure_regions.json"
    reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.is_file() else {}
    pending = []
    for item in documents:
        result = work / item["id"] / "result.json"
        if result.exists() and json.loads(result.read_text()).get("recipe") == recipe:
            continue
        pending.append(item)
    logger.info("Processing %d PDFs across %d tasks; %d pending", len(documents), len(tasks), len(pending))
    for offset in range(0, len(pending), args.batch_size):
        batch = pending[offset:offset + args.batch_size]
        batch_dir = create_batch(work, offset // args.batch_size)
        inputs, raw = batch_dir / "input", batch_dir / "raw"
        inputs.mkdir(parents=True, exist_ok=True)
        for item in batch:
            link = inputs / f"{item['id']}.pdf"
            if not link.exists():
                link.symlink_to(PROJECT_ROOT / item["pdf_path"])
        batch_error = None
        try:
            _, batch_failures = run_pdffigures2_batch(inputs, raw, [item["id"] for item in batch], pdffigures2_dir=checkout,
                                 jar=jar, dpi=args.dpi, image_format="png", threads=args.threads, logger=logger)
        except Exception as exc:
            batch_error = str(exc)
            logger.exception("Batch extractor failed")
        for item in batch:
            pdf = PROJECT_ROOT / item["pdf_path"]
            directory = work / item["id"]
            directory.mkdir(exist_ok=True)
            assets, unmatched, status, error = [], [], "ok", None
            try:
                if batch_error:
                    raise RuntimeError(batch_error)
                if item["id"] in batch_failures:
                    raise RuntimeError("PDFFigures2 produced no document metadata")
                assets, unmatched = export_assets(pdf, raw / f"{item['id']}.json", directory, dpi=args.dpi)
            except Exception as exc:
                error = str(exc)
                status = "error"
                entry = reviewed.get(f"{item['task_id']}|{item['pdf_url']}")
                if entry:
                    assets = reviewed_fallback(entry, item, pdf, checksum(pdf))
                    status = "partial"
                logger.warning("%s %s: %s", status, item["id"], error)
            for asset in assets + unmatched:
                asset.update(task_id=item["task_id"], pdf_url=item["pdf_url"], role=item["role"])
            fields = stage_publication(assets, unmatched, directory, directory / "public", pdf.parent,
                                       project_root=PROJECT_ROOT, status=status, error=error)
            result = {**item, "recipe": recipe, "status": status, "error": error, "fields": fields,
                      "raw_metadata_path": str((raw / f"{item['id']}.json").relative_to(work)),
                      "assets": len(assets), "unmatched_captions": len(unmatched),
                      "missing_caption_text": sum(not asset.get("caption") for asset in assets),
                      "clipped_caption_assets": sum(asset.get("caption_boundary_clipped", False) for asset in assets),
                      "continuation_pages": sum(max(0, len(asset.get("pages", [])) - 1) for asset in assets)}
            write_json(directory / "result.json", result)
        logger.info("Batch finished; %d/%d pending documents processed", min(offset + len(batch), len(pending)), len(pending))
    finalize_run(tasks, documents, work, snapshot, dpi=args.dpi, do_publish=args.publish)


if __name__ == "__main__":
    main()
