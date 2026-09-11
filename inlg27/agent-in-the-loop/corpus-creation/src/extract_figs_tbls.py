#!/usr/bin/env python
"""Stage 6 — extract captioned figures and tables with AllenAI PDFFigures2.

Liteparse provides the canonical Markdown and extracts raster images that are embedded
in the PDF.  PDFFigures2 is run as a second, independent extractor because it also
detects captioned figures and tables (including many vector-rendered figures) and
renders them to image files.  Its outputs are copied into the document-local
``figures/`` and ``tables/`` directories rather than a separate parallel tree.

The stage is deliberately resumable.  It records the files produced by PDFFigures2 in
``data/final/manifest.jsonl`` and only re-runs a document when that record is absent or
one of its recorded files has disappeared.  Files written by this extractor are prefixed
with ``pdffigures2-`` so they cannot overwrite Liteparse assets or the cropped table
images produced by ``parse_fulltext.py``.

Setup (from ``corpus-creation/``)::

    mkdir -p third_party
    git clone https://github.com/allenai/pdffigures2.git third_party/pdffigures2
    (cd third_party/pdffigures2 && sbt assembly)

The resulting JAR can be passed with ``--pdffigures2-jar``.  Without a JAR, the stage
invokes ``sbt -batch`` directly, matching the supplied PDFFigures2 wrapper.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import (
    MANIFEST_PATH,
    document_figures_dir,
    document_pdf_path,
    document_tables_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_PDFFIGURES2_DIR = PROJECT_ROOT / "third_party" / "pdffigures2"
DEFAULT_DPI = 150
DEFAULT_IMAGE_FORMAT = "png"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
OUTPUT_PREFIX = "pdffigures2-"


def setup_logging() -> Path:
    """Create a readable stage log using the requested write/truncate mode."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"extract_figs_tbls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    return log_path


def load_tasks(confidence: str, task_id: str | None) -> list[dict]:
    """Load the same candidate selection used by the surrounding pipeline stages."""
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"missing {CANDIDATES_PATH} — run group_tasks.py first")

    tasks = [
        json.loads(line)
        for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if confidence != "all":
        tasks = [task for task in tasks if task["provenance"]["confidence"] == confidence]
    if task_id:
        tasks = [task for task in tasks if task["task_id"] == task_id]
        if not tasks:
            raise ValueError(f"task_id {task_id} not found in the selected candidates")
    return tasks


def iter_documents(tasks: list[dict]):
    """Yield every overview and participant PDF in a stable, auditable order."""
    for task in tasks:
        yield task["task_id"], "overview", task["overview"]["pdf_url"]
        for participant in task["participants"]:
            yield task["task_id"], "participant", participant["pdf_url"]


def resolve_pdffigures2(
    pdffigures2_dir: Path,
    jar: Path | None,
) -> tuple[Path, Path | None]:
    """Resolve the checkout and optional assembled JAR, failing before any work starts."""
    if jar is not None:
        jar = jar.expanduser().resolve()
        if not jar.is_file():
            raise FileNotFoundError(f"PDFFigures2 JAR does not exist: {jar}")
        if shutil.which("java") is None:
            raise RuntimeError("Required command not found: java")
        return jar.parent, jar

    checkout = pdffigures2_dir.expanduser().resolve()
    if not checkout.is_dir():
        raise FileNotFoundError(
            f"PDFFigures2 directory does not exist: {checkout}. Clone it from "
            "https://github.com/allenai/pdffigures2"
        )

    candidate = checkout / "pdffigures2.jar"
    if candidate.is_file():
        if shutil.which("java") is None:
            raise RuntimeError("Required command not found: java")
        return checkout, candidate

    if shutil.which("sbt") is None:
        raise RuntimeError(
            "Required command not found: sbt. Install sbt, or provide a built "
            "PDFFigures2 JAR with --pdffigures2-jar."
        )
    return checkout, None


def pdffigures2_command(
    input_file: Path,
    output_dir: Path,
    *,
    pdffigures2_dir: Path,
    jar: Path | None,
    dpi: int,
    image_format: str,
) -> list[str]:
    """Build the Java/SBT command used by the supplied PDFFigures2 wrapper."""
    output_dir.mkdir(parents=True, exist_ok=True)
    arguments = [
        str(input_file.resolve()),
        "-m", str(output_dir.resolve()) + os.sep,
        "-d", str(output_dir.resolve()) + os.sep,
        "-i", str(dpi),
        "-f", image_format,
        "-c",
        "-q",
    ]
    if jar is not None:
        return [
            "java",
            "-Dsun.java2d.cmm=sun.java2d.cmm.kcms.KcmsServiceProvider",
            "-jar",
            str(jar.resolve()),
            *arguments,
        ]

    command_text = shlex.join([
        "runMain",
        "org.allenai.pdffigures2.FigureExtractorBatchCli",
        *arguments,
    ])
    return ["sbt", "-batch", command_text]


def pdffigures2_batch_command(
    input_dir: Path,
    output_dir: Path,
    *,
    pdffigures2_dir: Path,
    jar: Path | None,
    dpi: int,
    image_format: str,
    threads: int,
) -> list[str]:
    """Build one batch command for all pending PDFs.

    The reference wrapper invokes the CLI once per file. The CLI also accepts a
    directory and supports multiple worker threads; using that mode keeps the JVM startup
    cost from being paid once per document during a corpus build.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    arguments = [
        str(input_dir.resolve()),
        "-m", str(output_dir.resolve()) + os.sep,
        "-d", str(output_dir.resolve()) + os.sep,
        "-i", str(dpi),
        "-f", image_format,
        "-c",
        "-q",
        "-e",
        "-t", str(threads),
    ]
    if jar is not None:
        return [
            "java",
            "-Dsun.java2d.cmm=sun.java2d.cmm.kcms.KcmsServiceProvider",
            "-jar",
            str(jar.resolve()),
            *arguments,
        ]

    command_text = shlex.join([
        "runMain",
        "org.allenai.pdffigures2.FigureExtractorBatchCli",
        *arguments,
    ])
    return ["sbt", "-batch", command_text]


def image_files(output_dir: Path) -> list[Path]:
    """Find rendered image files recursively, tolerating PDFFigures2 subdirectories."""
    return sorted(
        path for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def classify_image(path: Path) -> str | None:
    """Classify a PDFFigures2 image from its conventional Figure/Table filename."""
    name = path.stem.lower()
    if re.search(r"(?:^|[-_.])table(?:[-_.]|\d|$)", name):
        return "tables"
    if re.search(r"(?:^|[-_.])(?:figure|fig)(?:[-_.]|\d|$)", name):
        return "figures"
    # The standard output is e.g. paper-Figure1-1.png. Keep a conservative fallback for
    # a future PDFFigures2 naming variant, but never silently call an unknown file a table.
    if "table" in name:
        return "tables"
    if "figure" in name or "fig" in name:
        return "figures"
    return None


def relative_project_path(path: Path) -> str:
    """Return a manifest path relative to the corpus-creation project root."""
    return str(path.resolve().relative_to(PROJECT_ROOT))


def remove_previous_outputs(figures_dir: Path, tables_dir: Path) -> None:
    """Remove extractor outputs and legacy table assets.

    The first version of the pipeline wrote ``table-NN.md`` and
    ``pageNNN-tableNN.png`` files from Liteparse. PDFFigures2 is now the single
    table extractor, so those files must be removed even on a cache hit.
    Embedded Liteparse figures are preserved.
    """
    for directory in (figures_dir, tables_dir):
        if not directory.is_dir():
            continue
        for path in directory.glob(f"{OUTPUT_PREFIX}*"):
            if path.is_file():
                path.unlink()
    if tables_dir.is_dir():
        for pattern in ("table-*.md", "page*-table*.png"):
            for path in tables_dir.glob(pattern):
                if path.is_file():
                    path.unlink()


def cached_extraction(record: dict | None) -> bool:
    """Whether all previously recorded PDFFigures2 files are still present."""
    if not record or record.get("pdffigures2_status") != "ok":
        return False
    files = record.get("pdffigures2_files")
    if not isinstance(files, list):
        return False
    return all((PROJECT_ROOT / path).is_file() for path in files)


def refresh_asset_counts(record: dict, figures_dir: Path, tables_dir: Path) -> dict:
    """Refresh aggregate asset counts for the final document-local assets."""
    # These directories are part of the public corpus layout, including for papers
    # where PDFFigures2 found no assets.
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_files = sorted(path for path in figures_dir.glob("*") if path.is_file()) if figures_dir.is_dir() else []
    table_files = sorted(path for path in tables_dir.glob("*") if path.is_file()) if tables_dir.is_dir() else []
    record["figures_dir"] = relative_project_path(figures_dir)
    record["n_figures"] = len(figure_files)
    record["tables_dir"] = relative_project_path(tables_dir)
    # PDFFigures2 table images are the only table representation in the final
    # corpus. Keep the legacy aggregate fields aligned for existing consumers.
    record["n_tables"] = len(table_files)
    record["n_table_images"] = len(table_files)
    return record


def run_pdffigures2(
    input_file: Path,
    output_dir: Path,
    *,
    pdffigures2_dir: Path,
    jar: Path | None,
    dpi: int,
    image_format: str,
    logger: logging.Logger,
) -> list[Path]:
    """Run PDFFigures2 in a temporary directory and return its image outputs."""
    command = pdffigures2_command(
        input_file,
        output_dir,
        pdffigures2_dir=pdffigures2_dir,
        jar=jar,
        dpi=dpi,
        image_format=image_format,
    )
    logger.info("PDFFigures2 command: %s", shlex.join(command))
    result = subprocess.run(
        command,
        cwd=pdffigures2_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        logger.info("PDFFigures2 stdout for %s:\n%s", input_file.name, result.stdout.strip())
    if result.stderr.strip():
        logger.info("PDFFigures2 stderr for %s:\n%s", input_file.name, result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"PDFFigures2 failed with exit code {result.returncode}")

    # The reference wrapper treats missing metadata as a failed extraction. We retain
    # that useful integrity check even though the metadata is intentionally discarded
    # with the temporary directory after the image files have been copied.
    metadata = list(output_dir.rglob("*.json"))
    if not metadata:
        raise RuntimeError(f"PDFFigures2 produced no metadata file in {output_dir}")
    outputs = image_files(output_dir)
    logger.info("PDFFigures2 produced %d image(s) for %s", len(outputs), input_file.name)
    return outputs


def run_pdffigures2_batch(
    input_dir: Path,
    output_dir: Path,
    input_stems: list[str],
    *,
    pdffigures2_dir: Path,
    jar: Path | None,
    dpi: int,
    image_format: str,
    threads: int,
    logger: logging.Logger,
) -> tuple[dict[str, list[Path]], list[str]]:
    """Run one PDFFigures2 process and map each temporary input stem to its images."""
    command = pdffigures2_batch_command(
        input_dir,
        output_dir,
        pdffigures2_dir=pdffigures2_dir,
        jar=jar,
        dpi=dpi,
        image_format=image_format,
        threads=threads,
    )
    logger.info(
        "PDFFigures2 batch command for %d PDF(s): %s",
        len(input_stems), shlex.join(command),
    )
    result = subprocess.run(
        command,
        cwd=pdffigures2_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        logger.info("PDFFigures2 batch stdout:\n%s", result.stdout.strip())
    if result.stderr.strip():
        logger.info("PDFFigures2 batch stderr:\n%s", result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"PDFFigures2 batch failed with exit code {result.returncode}")

    outputs_by_stem: dict[str, list[Path]] = {}
    failures: list[str] = []
    all_images = image_files(output_dir)
    for stem in input_stems:
        metadata_file = output_dir / f"{stem}.json"
        if not metadata_file.is_file():
            failures.append(stem)
            logger.error("PDFFigures2 produced no metadata for %s", stem)
            continue
        outputs_by_stem[stem] = sorted(
            path for path in all_images if path.name.startswith(f"{stem}-")
        )
        logger.info(
            "PDFFigures2 batch result %s: %d image(s)",
            stem, len(outputs_by_stem[stem]),
        )
    return outputs_by_stem, failures


def save_extracted_outputs(
    task_id: str,
    role: str,
    pdf_url: str,
    previous: dict | None,
    outputs: list[Path],
    *,
    dpi: int,
    image_format: str,
    logger: logging.Logger,
) -> dict:
    """Copy classified batch outputs into the document layout and update its manifest."""
    figures_dir = document_figures_dir(task_id, role, pdf_url)
    tables_dir = document_tables_dir(task_id, role, pdf_url)
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    remove_previous_outputs(figures_dir, tables_dir)

    record = dict(previous or {})
    written_figures: list[str] = []
    written_tables: list[str] = []
    unclassified = 0
    for source in outputs:
        kind = classify_image(source)
        if kind is None:
            unclassified += 1
            logger.warning("unclassified PDFFigures2 image ignored: %s", source.name)
            continue
        target_dir = figures_dir if kind == "figures" else tables_dir
        target = target_dir / f"{OUTPUT_PREFIX}{source.name}"
        shutil.copy2(source, target)
        relative = relative_project_path(target)
        (written_figures if kind == "figures" else written_tables).append(relative)

    if unclassified:
        logger.warning("%s: ignored %d unclassified PDFFigures2 image(s)", pdf_url, unclassified)
    files = sorted(written_figures + written_tables)
    record.update({
        "task_id": task_id,
        "role": role,
        "pdf_url": pdf_url,
        "pdffigures2_status": "ok",
        "pdffigures2_extractor": "allenai/pdffigures2",
        "pdffigures2_dpi": dpi,
        "pdffigures2_image_format": image_format,
        "pdffigures2_figures": len(written_figures),
        "pdffigures2_tables": len(written_tables),
        "pdffigures2_files": files,
        "pdffigures2_extracted_at": datetime.now().isoformat(timespec="seconds"),
        "pdffigures2_error": None,
    })
    refresh_asset_counts(record, figures_dir, tables_dir)
    logger.info(
        "%s: saved %d PDFFigures2 figure(s) and %d table(s)",
        pdf_url, len(written_figures), len(written_tables),
    )
    return record


def process_document(
    task_id: str,
    role: str,
    pdf_url: str,
    previous: dict | None,
    *,
    pdffigures2_dir: Path,
    jar: Path | None,
    dpi: int,
    image_format: str,
    logger: logging.Logger,
) -> dict:
    """Extract one PDF and merge the result into its existing manifest record."""
    pdf_path = document_pdf_path(task_id, role, pdf_url)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"missing PDF: {pdf_path} — run download_papers.py first")

    record = dict(previous or {})
    figures_dir = document_figures_dir(task_id, role, pdf_url)
    tables_dir = document_tables_dir(task_id, role, pdf_url)
    if cached_extraction(record):
        logger.info("PDFFigures2 cache hit: %s", pdf_path)
        remove_previous_outputs(figures_dir, tables_dir)
        return refresh_asset_counts(record, figures_dir, tables_dir)

    with tempfile.TemporaryDirectory(prefix="pdffigures2-") as temp_dir:
        extractor_output = Path(temp_dir) / f"{pdf_path.stem}_figs_tbls"
        outputs = run_pdffigures2(
            pdf_path,
            extractor_output,
            pdffigures2_dir=pdffigures2_dir,
            jar=jar,
            dpi=dpi,
            image_format=image_format,
            logger=logger,
        )
        return save_extracted_outputs(
            task_id,
            role,
            pdf_url,
            record,
            outputs,
            dpi=dpi,
            image_format=image_format,
            logger=logger,
        )


def load_manifest() -> tuple[list[dict], dict[str, dict]]:
    """Load the text manifest while preserving its current order."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"missing {MANIFEST_PATH} — run parse_fulltext.py first")
    records = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records, {record["pdf_url"]: record for record in records}


def write_manifest(records: list[dict]) -> None:
    """Rewrite the generated manifest atomically in readable JSONL form."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract captioned figures and tables into each document's figures/ and tables/ directories."
    )
    parser.add_argument("--task-id", help="Process only this task.")
    parser.add_argument("--confidence", choices=["high", "medium", "all"], default="high")
    parser.add_argument(
        "--pdffigures2-dir",
        type=Path,
        default=Path(os.getenv("PDFFIGURES2_DIR", DEFAULT_PDFFIGURES2_DIR)),
        help="PDFFigures2 checkout containing build.sbt or pdffigures2.jar.",
    )
    parser.add_argument("--pdffigures2-jar", type=Path, help="Use a built PDFFigures2 JAR instead of sbt.")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--image-format", choices=["png", "jpg", "jpeg"], default=DEFAULT_IMAGE_FORMAT)
    parser.add_argument("--threads", type=int, default=4, help="PDFFigures2 worker threads for the batch run.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("extract_figs_tbls")
    logger.info("logging to %s", log_path)
    logger.info("data root: %s", PROJECT_ROOT / "data")

    if args.dpi <= 0 or args.threads <= 0:
        logger.error("--dpi and --threads must be positive")
        raise SystemExit(2)

    try:
        tasks = load_tasks(args.confidence, args.task_id)
        manifest_records, manifest_by_url = load_manifest()
        checkout, jar = resolve_pdffigures2(args.pdffigures2_dir, args.pdffigures2_jar)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.error("cannot start figure/table extraction: %s", exc)
        raise SystemExit(1)

    documents = list(iter_documents(tasks))
    logger.info(
        "processing %d document(s) with PDFFigures2 (confidence=%s, jar=%s)",
        len(documents), args.confidence, jar or "sbt",
    )
    failures: list[tuple[str, str]] = []
    pending: list[dict] = []

    def mark_failure(task_id: str, role: str, pdf_url: str, previous: dict | None, message: str) -> None:
        """Record a failed document without discarding the rest of the batch."""
        failures.append((pdf_url, message))
        figures_dir = document_figures_dir(task_id, role, pdf_url)
        tables_dir = document_tables_dir(task_id, role, pdf_url)
        figures_dir.mkdir(parents=True, exist_ok=True)
        tables_dir.mkdir(parents=True, exist_ok=True)
        failed_record = dict(previous or {})
        failed_record.update({
            "task_id": task_id,
            "role": role,
            "pdf_url": pdf_url,
            "figures_dir": relative_project_path(figures_dir),
            "tables_dir": relative_project_path(tables_dir),
            "pdffigures2_status": "error",
            "pdffigures2_error": message,
            "pdffigures2_extracted_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest_by_url[pdf_url] = failed_record

    for index, (task_id, role, pdf_url) in enumerate(documents, start=1):
        logger.info("[%d/%d] %s %s", index, len(documents), task_id, role)
        previous = manifest_by_url.get(pdf_url)
        try:
            pdf_path = document_pdf_path(task_id, role, pdf_url)
            figures_dir = document_figures_dir(task_id, role, pdf_url)
            tables_dir = document_tables_dir(task_id, role, pdf_url)
            if not pdf_path.is_file():
                raise FileNotFoundError(f"missing PDF: {pdf_path} — run download_papers.py first")
            if cached_extraction(previous):
                logger.info("PDFFigures2 cache hit: %s", pdf_path)
                manifest_by_url[pdf_url] = refresh_asset_counts(dict(previous), figures_dir, tables_dir)
                continue
            # Only remove stale outputs after the cache check. Removing them first would
            # make every valid cache entry fail its own existence test.
            remove_previous_outputs(figures_dir, tables_dir)
            pending.append({
                "task_id": task_id,
                "role": role,
                "pdf_url": pdf_url,
                "previous": previous,
                "pdf_path": pdf_path,
                "stem": f"document-{index:04d}-{pdf_path.stem}",
            })
        except Exception as exc:  # continue so one bad PDF does not hide later failures
            message = str(exc)
            mark_failure(task_id, role, pdf_url, previous, message)
            logger.exception("PDFFigures2 failed for %s", pdf_url)

    if pending:
        logger.info("running one PDFFigures2 batch for %d pending document(s)", len(pending))
        with tempfile.TemporaryDirectory(prefix="pdffigures2-batch-") as temp_dir:
            temp_root = Path(temp_dir)
            input_dir = temp_root / "input"
            output_dir = temp_root / "output"
            input_dir.mkdir()
            stems = []
            for item in pending:
                stem = item["stem"]
                link = input_dir / f"{stem}.pdf"
                try:
                    link.symlink_to(item["pdf_path"])
                except OSError:
                    # Symlinks keep the batch cheap; copying is a portable fallback.
                    shutil.copy2(item["pdf_path"], link)
                stems.append(stem)

            try:
                outputs_by_stem, batch_failures = run_pdffigures2_batch(
                    input_dir,
                    output_dir,
                    stems,
                    pdffigures2_dir=checkout,
                    jar=jar,
                    dpi=args.dpi,
                    image_format=args.image_format,
                    threads=args.threads,
                    logger=logger,
                )
            except Exception as exc:
                logger.exception("PDFFigures2 batch failed")
                for item in pending:
                    mark_failure(item["task_id"], item["role"], item["pdf_url"], item["previous"], str(exc))
            else:
                failed_stems = set(batch_failures)
                for item in pending:
                    if item["stem"] in failed_stems:
                        mark_failure(
                            item["task_id"],
                            item["role"],
                            item["pdf_url"],
                            item["previous"],
                            "PDFFigures2 produced no per-document metadata",
                        )
                        continue
                    record = save_extracted_outputs(
                        item["task_id"],
                        item["role"],
                        item["pdf_url"],
                        item["previous"],
                        outputs_by_stem[item["stem"]],
                        dpi=args.dpi,
                        image_format=args.image_format,
                        logger=logger,
                    )
                    manifest_by_url[item["pdf_url"]] = record

    # Keep documents not selected by --task-id/--confidence in place. Append newly
    # discovered records only for completeness; a normal pipeline run updates all of its
    # selected manifest entries in their original parse order.
    ordered = []
    seen = set()
    for record in manifest_records:
        url = record["pdf_url"]
        ordered.append(manifest_by_url.get(url, record))
        seen.add(url)
    for url, record in manifest_by_url.items():
        if url not in seen:
            ordered.append(record)
    write_manifest(ordered)

    ok = len(documents) - len(failures)
    logger.info("completed PDFFigures2 extraction for %d/%d document(s)", ok, len(documents))
    if failures:
        # Match the supplied wrapper's directory-mode behavior: an upstream PDF parsing
        # problem is recorded for review, but must not discard the successful extractions
        # or prevent the metadata/count/code stages from completing.
        for pdf_url, message in failures:
            logger.error("FAILED (recorded in manifest; Liteparse assets preserved): %s — %s", pdf_url, message)
        logger.warning("%d document(s) could not be processed by PDFFigures2; see manifest.jsonl", len(failures))


if __name__ == "__main__":
    main()
