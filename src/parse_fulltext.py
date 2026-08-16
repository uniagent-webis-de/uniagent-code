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
import tempfile
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Reads the candidate list rather than the assembled corpus: build_corpus.py joins this
# stage's manifest to publish fulltext paths, so depending on its output would be circular.
CANDIDATES_PATH = PROJECT_ROOT / "data" / "intermediate" / "all_candidates.jsonl"
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


TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def split_markdown_tables(markdown: str) -> list[list[str]]:
    """Return each pipe-table in the document as its list of raw lines.

    liteparse already renders tables into GitHub-style markdown, so tables are recovered
    from the parsed text rather than re-derived from the PDF. A run of consecutive lines
    starting with "|" is a table; a lone such line is prose containing a pipe, not a
    table, so at least two lines are required."""
    tables, current = [], []
    for line in markdown.splitlines():
        if line.lstrip().startswith("|"):
            current.append(line.rstrip())
            continue
        if len(current) >= 2:
            tables.append(current)
        current = []
    if len(current) >= 2:
        tables.append(current)
    return tables


def table_to_rows(table_lines: list[str]) -> list[list[str]]:
    """Split a markdown table into cells, dropping the |---|---| separator row."""
    rows = []
    for line in table_lines:
        if TABLE_SEPARATOR_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


# Rendering resolution for cropped table images. 150 DPI keeps the glyphs crisp; going
# lower and downscaling actually produced *larger* files, because the resampling blurs
# the text and defeats PNG compression.
TABLE_IMAGE_DPI = 150
POINTS_PER_INCH = 72
TABLE_CROP_PADDING_PT = 8

# A booktabs rule spans the text column; the short rule above a footnote block is ~56pt
# and must not be mistaken for a table.
MIN_RULE_LENGTH_PT = 100
# Two rules belong to the same table when they are vertically close and share most of
# their horizontal extent.
MAX_RULE_GAP_PT = 260


def horizontal_rules(page: dict) -> list[dict]:
    """Horizontal ruling lines on a page, long enough to be table rules, top to bottom."""
    lines = (page.get("vector_graphics") or {}).get("lines") or []
    rules = [
        line for line in lines
        if abs(line["y1"] - line["y2"]) < 1 and (line["x2"] - line["x1"]) > MIN_RULE_LENGTH_PT
    ]
    return sorted(rules, key=lambda line: line["y1"])


def group_rules_into_tables(rules: list[dict]) -> list[dict]:
    """Cluster ruling lines into table regions.

    LaTeX tables are delimited by a top rule, optional mid rules and a bottom rule, so a
    run of nearby rules sharing an x-extent bounds exactly one table. This is far more
    reliable than inferring the extent from matched text, which under-runs when the
    matched cells are sparse and over-runs into body text when a cell string recurs."""
    if not rules:
        return []
    groups: list[list[dict]] = [[rules[0]]]
    for previous, current in zip(rules, rules[1:]):
        overlap = min(previous["x2"], current["x2"]) - max(previous["x1"], current["x1"])
        same_table = (
            current["y1"] - previous["y1"] < MAX_RULE_GAP_PT
            and overlap > 0.5 * (previous["x2"] - previous["x1"])
        )
        groups[-1].append(current) if same_table else groups.append([current])

    regions = []
    for group in groups:
        # A single isolated rule is a separator, not a table.
        if len(group) < 2:
            continue
        regions.append({
            "x0": min(line["x1"] for line in group),
            "x1": max(line["x2"] for line in group),
            "y0": group[0]["y1"],
            "y1": group[-1]["y1"],
        })
    return regions


def page_geometry(pdf_path: Path, logger: logging.Logger) -> list[dict]:
    """Per-page text items and vector rules, parsed once per document."""
    result = subprocess.run(
        ["lit", "parse", str(pdf_path), "--format", "json", "--no-ocr",
         "--extract-vector-graphics", "-o", "/dev/stdout", "-q"],
        capture_output=True, text=True,
    )
    try:
        return json.loads(result.stdout).get("pages") or []
    except (json.JSONDecodeError, TypeError):
        logger.warning("could not read page geometry for %s — table images skipped", pdf_path.name)
        return []


def locate_table(table_lines: list[str], pages: list[dict]) -> tuple[int, dict] | None:
    """Find the page and bounding box of one markdown table.

    Distinctive cell strings anchor the table to a page and a vertical position; the
    ruling lines around that position give the actual crop box."""
    cells = [cell for row in table_to_rows(table_lines) for cell in row if len(cell) > 4]
    if not cells:
        return None

    best_page, best_hits = None, []
    for page in pages:
        hits = [item for item in (page.get("text_items") or []) if any(c in item["text"] for c in cells)]
        if len(hits) > len(best_hits):
            best_page, best_hits = page, hits
    if best_page is None or not best_hits:
        return None

    regions = group_rules_into_tables(horizontal_rules(best_page))
    if not regions:
        return None

    # Pick the ruled region containing the most of this table's matched text.
    def contained(region: dict) -> int:
        return sum(1 for h in best_hits if region["y0"] - 4 <= h["y"] <= region["y1"] + 4)

    if regions:
        region = max(regions, key=contained)
        if contained(region):
            return best_page["page"], region

    # Unruled table (no booktabs rules on that page): fall back to the text block itself.
    # Seed from the matched cells, then grow through vertically adjacent lines so the crop
    # covers the whole table rather than only the rows whose text happened to match.
    return best_page["page"], text_block_region(best_page, best_hits)


def text_block_region(page: dict, hits: list[dict]) -> dict | None:
    """Bounding box of the contiguous block of text lines containing the matched cells."""
    items = page.get("text_items") or []
    if not items or not hits:
        return None
    x0 = min(h["x"] for h in hits)
    x1 = max(h["x"] + h["width"] for h in hits)
    line_height = max(h["height"] for h in hits) or 10

    # Only lines overlapping the matched columns can belong to this table.
    column = sorted(
        (i for i in items if i["x"] + i["width"] > x0 - line_height and i["x"] < x1 + line_height),
        key=lambda i: i["y"],
    )
    y0 = min(h["y"] for h in hits)
    y1 = max(h["y"] + h["height"] for h in hits)
    changed = True
    while changed:
        changed = False
        for item in column:
            top, bottom = item["y"], item["y"] + item["height"]
            if bottom < y0 - 2 * line_height or top > y1 + 2 * line_height:
                continue
            if top < y0 or bottom > y1:
                y0, y1 = min(y0, top), max(y1, bottom)
                changed = True

    # A block taller than half the page is body text, not a table — refuse rather than
    # ship a crop that is mostly prose.
    if (y1 - y0) > 0.5 * page.get("height", 792):
        return None
    return {
        "x0": min(i["x"] for i in column if y0 - 2 <= i["y"] <= y1 + 2),
        "x1": max(i["x"] + i["width"] for i in column if y0 - 2 <= i["y"] <= y1 + 2),
        "y0": y0,
        "y1": y1,
    }


def render_table_images(pdf_path: Path, located: dict[int, tuple[int, dict]], tables_dir: Path, logger: logging.Logger) -> int:
    """Crop each located table out of a rendered page image."""
    if not located:
        return 0
    from PIL import Image

    pages_needed = sorted({page for page, _ in located.values()})
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["lit", "screenshot", str(pdf_path), "--target-pages", ",".join(str(p) for p in pages_needed),
             "--dpi", str(TABLE_IMAGE_DPI), "-o", tmp, "-q"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.warning("page render failed for %s — table images skipped", pdf_path.name)
            return 0

        scale = TABLE_IMAGE_DPI / POINTS_PER_INCH
        written = 0
        for index, (page_number, region) in sorted(located.items()):
            page_image = Path(tmp) / f"page_{page_number}.png"
            if not page_image.exists():
                continue
            with Image.open(page_image) as image:
                pad = TABLE_CROP_PADDING_PT
                box = (
                    max(0, int((region["x0"] - pad) * scale)),
                    max(0, int((region["y0"] - pad) * scale)),
                    min(image.width, int((region["x1"] + pad) * scale)),
                    min(image.height, int((region["y1"] + pad) * scale)),
                )
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                # Grayscale: these are black-on-white tables, and it roughly halves the
                # file size with no loss of legibility.
                image.crop(box).convert("L").save(tables_dir / f"table-{index:02d}.png", optimize=True)
                written += 1
    return written


def write_tables(markdown: str, tables_dir: Path, pdf_path: Path | None = None, logger: logging.Logger | None = None) -> tuple[int, int]:
    """Write each table as verbatim markdown, plus a cropped image of it from the PDF.

    Tables stay inline in the document as well — these files are an additional view, not
    a removal, so the parsed paper still reads as a whole. Returns (tables, images)."""
    tables = split_markdown_tables(markdown)
    if not tables:
        return 0, 0
    tables_dir.mkdir(parents=True, exist_ok=True)
    for index, table_lines in enumerate(tables, start=1):
        (tables_dir / f"table-{index:02d}.md").write_text("\n".join(table_lines) + "\n", encoding="utf-8")

    if pdf_path is None or logger is None:
        return len(tables), 0

    pages = page_geometry(pdf_path, logger)
    located = {}
    for index, table_lines in enumerate(tables, start=1):
        found = locate_table(table_lines, pages)
        if found and found[1]:
            located[index] = found
    images = render_table_images(pdf_path, located, tables_dir, logger)
    if images < len(tables):
        logger.info("%s: %d/%d tables could be imaged (unruled tables have markdown only)", pdf_path.name, images, len(tables))
    return len(tables), images


def rewrite_figure_refs(markdown_path: Path, figures_rel_prefix: str) -> None:
    """liteparse emits bare filenames (![](img_p2_1.png)), which only resolve if the
    images sit beside the markdown. Figures are grouped in their own directory instead,
    so the references are rewritten to point there and stay clickable."""
    text = markdown_path.read_text(encoding="utf-8")
    rewritten = re.sub(r"!\[\]\((img_[^/)]+)\)", rf"![]({figures_rel_prefix}/\1)", text)
    if rewritten != text:
        markdown_path.write_text(rewritten, encoding="utf-8")


def parse_document(pdf_path: Path, out_path: Path, ocr_server_url: str | None, ocr_language: str, logger: logging.Logger, figures_dir: Path | None = None) -> bool:
    """Parse one PDF to markdown. Returns True on success."""
    command = ["lit", "parse", str(pdf_path), "--format", "markdown", "-o", str(out_path), "-q"]
    if figures_dir is not None:
        command += ["--extract-images", "--image-mode", "embed", "--image-output-dir", str(figures_dir)]
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

    # Overview at the task root, notebook papers grouped under participants/ — keeps the
    # target output visibly separate from the inputs it is generated from.
    out_path = out_dir / "overview.md" if role == "overview" else out_dir / "participants" / f"{stem}.md"

    # Assets are grouped by kind and keyed by document, so a task folder stays readable:
    #   {task}/figures/{doc}/img_p2_1.png   {task}/tables/{doc}/table-01.md
    doc_key = "overview" if role == "overview" else stem
    figures_dir = out_dir / "figures" / doc_key
    tables_dir = out_dir / "tables" / doc_key
    # Relative prefix from the markdown file back to its figures directory.
    figures_rel_prefix = f"figures/{doc_key}" if role == "overview" else f"../figures/{doc_key}"

    if out_path.exists():
        logger.info("fulltext cache hit: %s", out_path)
        text = out_path.read_text(encoding="utf-8")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
        if not parse_document(pdf_path, out_path, ocr_server_url, ocr_language, logger, figures_dir):
            return None
        rewrite_figure_refs(out_path, figures_rel_prefix)
        text = out_path.read_text(encoding="utf-8")
        write_tables(text, tables_dir, pdf_path, logger)
        if not any(figures_dir.iterdir()):
            figures_dir.rmdir()
        logger.info("parsed %s -> %s (%d chars)", pdf_path.name, out_path, len(text))

    figures = sorted(p.name for p in figures_dir.glob("*")) if figures_dir.exists() else []
    tables = sorted(p.name for p in tables_dir.glob("*.md")) if tables_dir.exists() else []
    table_images = sorted(p.name for p in tables_dir.glob("*.png")) if tables_dir.exists() else []

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
        "figures_dir": str(figures_dir.relative_to(PROJECT_ROOT)) if figures else None,
        "n_figures": len(figures),
        "tables_dir": str(tables_dir.relative_to(PROJECT_ROOT)) if tables else None,
        "n_tables": len(tables),
        "n_table_images": len(table_images),
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

    {{task_id}}/overview.md                    the task's overview paper (the target output)
    {{task_id}}/participants/{{paper_stem}}.md   one file per notebook paper (the inputs)
    {{task_id}}/figures/{{doc}}/img_p4_1.png     figures, grouped per document
    {{task_id}}/tables/{{doc}}/table-01.md       table as verbatim markdown
    {{task_id}}/tables/{{doc}}/table-01.png      the same table cropped from the page

`{{doc}}` is `overview` or the notebook paper's stem. Figures are raster images embedded
in the PDF, and the markdown keeps an inline `![](...)` reference to each one, so a
document still reads as a whole. Tables are handled the same way: markdown for the text,
plus an image of the table exactly as it appears in the paper, which preserves the
column layout, spanning headers and alignment that a flattened text version loses.
Tables also stay inline in the markdown — these files are an extra view, not a removal.

Table images are cropped using the paper's own ruling lines. A table that is drawn
without rules, or a block that the parser rendered as a table but is not one, gets
markdown only rather than a crop that might be mispositioned; `manifest.jsonl` records
`n_tables` alongside `n_table_images` so the gap is visible.

Note that figures drawn as vector graphics (many plots and diagrams) are not raster
images and are therefore not extracted as files; their captions remain in the text.

`{{paper_stem}}` matches the source PDF filename on CEUR-WS, so a document can always be
traced back to its origin. `manifest.jsonl` records, per document: `task_id`, `role`,
source `pdf_url`, output `markdown_path`, `chars`, `pages`, `chars_per_page`, whether an
OCR server was used, and whether the text layer looked too thin to trust (`needs_ocr`).

## Aligning with the corpus files

`shared_tasks.jsonl` carries the path to each parsed document directly, so no filename
munging is needed:

    task["overview"]["fulltext_path"]        -> {{task_id}}/overview.md
    task["participants"][i]["fulltext_path"] -> {{task_id}}/participants/....md

In `shared_tasks.csv`, `overview_fulltext_path` holds the overview and
`participant_fulltext_paths` holds the notebook papers joined by `; ` in the same order
as `participant_pdf_urls`, so the two columns line up positionally. A path is empty only
when that document could not be parsed.

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
    parser.add_argument("--confidence", type=str, default="high", choices=["high", "medium", "all"], help="Which candidate tasks to parse (default: high, matching build_corpus.py).")
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

    if not CANDIDATES_PATH.exists():
        logger.error("missing %s — run group_tasks.py first", CANDIDATES_PATH)
        sys.exit(1)

    tasks = [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()]
    if args.confidence != "all":
        tasks = [t for t in tasks if t["provenance"]["confidence"] == args.confidence]
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
