#!/usr/bin/env python
"""Stage 7 — parse the full text of every overview and notebook PDF in the final corpus,
so participants receive pre-parsed documents rather than just links.

PLAN.md section 7 originally listed text parsing as out of scope for the corpus builder;
it was added later by request, and lives here as its own re-runnable stage rather than
being folded into Stage 4/5 (which parse opportunistically for counts and code links).

OCR: liteparse cannot load a HuggingFace model directly — it delegates OCR to an HTTP
server via --ocr-server-url. To use PaddleOCR-VL, serve it and pass --ocr-server-url.
The default is the PDF's own text layer (--no-ocr), which every sampled CEUR working
note has, and which PLAN.md section 3 Stage 2 asks for ("Avoid OCR unless absolutely
necessary").
"""
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINAL_CORPUS_PATH = PROJECT_ROOT / "data" / "final" / "shared_tasks.jsonl"
PDF_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "pdf"
FULLTEXT_DIR = PROJECT_ROOT / "data" / "final" / "fulltext"
MANIFEST_PATH = FULLTEXT_DIR / "manifest.jsonl"
LOGS_DIR = PROJECT_ROOT / "logs"

# A born-digital CEUR page carries roughly 2000-4000 characters. A document averaging
# below this is either scanned or has a broken text layer, and is worth re-parsing
# through an OCR server — reported rather than silently accepted.
MIN_CHARS_PER_PAGE = 200

# No genuine CEUR working note is under a couple of thousand characters; anything shorter
# means extraction failed regardless of what the page count says.
MIN_CHARS_PER_DOCUMENT = 2000


def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"parse_fulltext_{timestamp}.log"

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


def pdf_stem_for(pdf_url: str) -> str:
    """Local filename stem for a paper, matching the layout Stage 4/5 already cached."""
    import re

    stem = Path(urlparse(pdf_url).path).stem
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)


def probe_pdf(pdf_path: Path) -> tuple[int | None, bool]:
    """Return (page_count, liteparse_says_complex) from liteparse's complexity probe.

    `lit is-complex` signals its verdict through the exit code — non-zero means the
    document IS complex enough to need OCR, the way grep exits non-zero on no-match. An
    earlier version treated that as a command failure and discarded the (perfectly valid)
    JSON on stdout, so page count came back None precisely for the documents that needed
    OCR, which then skipped the thin-text-layer check entirely. Always parse stdout."""
    result = subprocess.run(
        ["lit", "is-complex", str(pdf_path), "--compact", "-q"],
        capture_output=True, text=True,
    )
    try:
        pages = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, result.returncode != 0
    return len(pages), result.returncode != 0


def parse_document(pdf_path: Path, out_path: Path, ocr_server_url: str | None, ocr_language: str, logger: logging.Logger) -> bool:
    """Parse one PDF to markdown. Returns True on success."""
    command = ["lit", "parse", str(pdf_path), "--format", "markdown", "-o", str(out_path), "-q"]
    if ocr_server_url:
        # Routing OCR to a server (e.g. a served PaddleOCR-VL) — do not pass --no-ocr,
        # otherwise liteparse would never call it.
        command += ["--ocr-server-url", ocr_server_url, "--ocr-language", ocr_language]
    else:
        command += ["--no-ocr"]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("lit parse failed for %s: %s", pdf_path, result.stderr.strip()[:300])
        return False
    return True


def process_document(task_id: str, role: str, pdf_url: str, out_dir: Path, ocr_server_url: str | None, ocr_language: str, logger: logging.Logger) -> dict | None:
    stem = pdf_stem_for(pdf_url)
    # Stage 4 caches the overview as "overview.pdf" while Stage 5 caches participants
    # under their URL-derived stem, so an overview must be looked up both ways.
    candidates = [PDF_RAW_DIR / task_id / f"{stem}.pdf"]
    if role == "overview":
        candidates.insert(0, PDF_RAW_DIR / task_id / "overview.pdf")
    pdf_path = next((c for c in candidates if c.exists()), None)
    if pdf_path is None:
        logger.warning("%s: missing cached PDF for %s — run extract_counts.py/find_code.py first", task_id, pdf_url)
        return None

    out_path = out_dir / f"{'overview' if role == 'overview' else stem}.md"
    if out_path.exists():
        logger.info("fulltext cache hit: %s", out_path)
        text = out_path.read_text(encoding="utf-8")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        if not parse_document(pdf_path, out_path, ocr_server_url, ocr_language, logger):
            return None
        text = out_path.read_text(encoding="utf-8")
        logger.info("parsed %s -> %s (%d chars)", pdf_path.name, out_path, len(text))

    pages, _ = probe_pdf(pdf_path)
    chars_per_page = round(len(text) / pages, 1) if pages else None

    # Fail loudly on a thin parse rather than shipping it silently (AGENT.md): too few
    # characters per page, an absolute character count no real paper would have, or a page
    # count that could not be established at all (treated as suspicious, not as a pass).
    #
    # liteparse's own is-complex verdict is deliberately NOT a trigger here: it fires on
    # ordinary tables, figures and vector graphics, and flagged 471 of 486 perfectly
    # well-extracted papers when tried. The text metrics below match the independent
    # 504-PDF scan exactly (one genuine case).
    reasons = []
    if chars_per_page is not None and chars_per_page < MIN_CHARS_PER_PAGE:
        reasons.append(f"only {chars_per_page} chars/page")
    if len(text) < MIN_CHARS_PER_DOCUMENT:
        reasons.append(f"only {len(text)} chars extracted in total")
    if pages is None:
        reasons.append("page count could not be determined")

    record = {
        "task_id": task_id,
        "role": role,
        "pdf_url": pdf_url,
        "markdown_path": str(out_path.relative_to(PROJECT_ROOT)),
        "chars": len(text),
        "pages": pages,
        "chars_per_page": chars_per_page,
        "ocr_server_used": bool(ocr_server_url),
        "needs_ocr": bool(reasons) and not ocr_server_url,
        "quality_flags": reasons,
    }
    if reasons:
        logger.warning(
            "%s: %s has a questionable text layer (%s)%s",
            task_id, out_path.name, "; ".join(reasons),
            "" if ocr_server_url else " — re-run with --ocr-server-url --only-needs-ocr",
        )
    return record


def write_readme(records: list[dict], path: Path) -> None:
    """Explain the layout to whoever receives this directory, so the corpus is usable
    without reading the manifest or the pipeline source."""
    overviews = sum(1 for r in records if r["role"] == "overview")
    participants = sum(1 for r in records if r["role"] == "participant")
    ocr_needed = sum(1 for r in records if r.get("needs_ocr"))
    path.write_text(
        f"""# Shared-task corpus — parsed full text

{overviews} overview papers and {participants} participant (notebook) papers, parsed from
the published CEUR-WS PDFs to Markdown.

## Layout

    {{task_id}}/overview.md      the task's overview paper (organizer-written)
    {{task_id}}/{{paper_stem}}.md  one file per participant/notebook paper

`{{paper_stem}}` matches the source PDF filename on CEUR-WS, so a document can always be
traced back to its origin. `manifest.jsonl` records, per document: `task_id`, `role`,
source `pdf_url`, output `markdown_path`, `chars`, `pages`, `chars_per_page`, whether an
OCR server was used, and whether the text layer looked too thin to trust (`needs_ocr`).

Task-level metadata (participants, counts, code links, coverage ratios) lives alongside
this directory in `shared_tasks.jsonl` / `shared_tasks.csv`, keyed by the same `task_id`.

## Parsing

Text comes from each PDF's own text layer via liteparse; CEUR working notes are
born-digital, so no OCR was required for {len(records) - ocr_needed} of {len(records)} documents.
{"All documents parsed cleanly." if not ocr_needed else f"{ocr_needed} document(s) have no usable text layer and are flagged `needs_ocr` in the manifest; regenerate those with an OCR server (see below)."}

To route OCR through a served model (for example PaddleOCR-VL):

    ./src/parse_fulltext.py --ocr-server-url http://localhost:8080 --only-needs-ocr

## Caveat for task design

Overview papers are the *target* output of this shared task. They are included here for
building and validating systems — withhold the overview text for any split used as a
blind test set, or the answer leaks.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse full text of corpus PDFs to markdown for participants.")
    parser.add_argument("--task-id", type=str, default=None, help="Parse only this task (for testing).")
    parser.add_argument("--ocr-server-url", type=str, default=None, help="HTTP OCR server URL (e.g. a served PaddleOCR-VL). Default: use the PDF's own text layer.")
    parser.add_argument("--ocr-language", type=str, default="eng", help="OCR language passed through to the OCR server (default: eng).")
    parser.add_argument("--only-needs-ocr", action="store_true", help="Re-parse only documents a previous run flagged as needing OCR.")
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("parse_fulltext")
    logger.info("logging to %s", log_path)
    if args.ocr_server_url:
        logger.info("OCR routed to server %s (language=%s)", args.ocr_server_url, args.ocr_language)
    else:
        logger.info("using each PDF's own text layer (--no-ocr); pass --ocr-server-url to route OCR to a server")

    if not FINAL_CORPUS_PATH.exists():
        logger.error("missing %s — run build_corpus.py first", FINAL_CORPUS_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in FINAL_CORPUS_PATH.read_text(encoding="utf-8").splitlines()]
    if args.task_id:
        tasks = [t for t in tasks if t["task_id"] == args.task_id]
        if not tasks:
            logger.error("task_id %s not found in the final corpus", args.task_id)
            sys.exit(1)

    retry_only: set[str] = set()
    if args.only_needs_ocr:
        if not MANIFEST_PATH.exists():
            logger.error("--only-needs-ocr needs a previous run's manifest at %s", MANIFEST_PATH)
            sys.exit(1)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("needs_ocr"):
                retry_only.add(record["pdf_url"])
                Path(PROJECT_ROOT / record["markdown_path"]).unlink(missing_ok=True)
        logger.info("re-parsing %d document(s) previously flagged as needing OCR", len(retry_only))

    records = []
    for task in tasks:
        task_dir = FULLTEXT_DIR / task["task_id"]
        documents = [("overview", task["overview"]["pdf_url"])]
        documents += [("participant", p["pdf_url"]) for p in task["participants"]]
        for role, pdf_url in documents:
            if retry_only and pdf_url not in retry_only:
                continue
            record = process_document(task["task_id"], role, pdf_url, task_dir, args.ocr_server_url, args.ocr_language, logger)
            if record:
                records.append(record)

    if retry_only and MANIFEST_PATH.exists():
        # Merge into the existing manifest so a targeted OCR re-run does not discard the
        # entries it did not touch.
        by_url = {json.loads(l)["pdf_url"]: json.loads(l) for l in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()}
        by_url.update({r["pdf_url"]: r for r in records})
        records = list(by_url.values())

    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    write_readme(records, FULLTEXT_DIR / "README.md")

    needs_ocr = [r for r in records if r.get("needs_ocr")]
    logger.info(
        "wrote %d documents (%d overviews, %d participants) to %s",
        len(records), sum(1 for r in records if r["role"] == "overview"),
        sum(1 for r in records if r["role"] == "participant"), FULLTEXT_DIR,
    )
    if needs_ocr:
        logger.warning("%d document(s) have a thin/missing text layer and need OCR — re-run with --ocr-server-url --only-needs-ocr", len(needs_ocr))
    else:
        logger.info("every document yielded a usable text layer; no OCR required")


if __name__ == "__main__":
    main()
