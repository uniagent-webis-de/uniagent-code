#!/usr/bin/env python
"""Optional stage — re-OCR scanned or garbled documents with a vision-language OCR model.

liteparse's bundled Tesseract reads columns and tables badly: words come out displaced and
two-column text interleaved. A VLM OCR model (default LightOnOCR-3-1B) reads the page layout
and returns clean Markdown in reading order. On the 10 worst OCR documents it raised a
word-order score (share of word pairs found in clean papers) from 0.64-0.70 to 0.66-0.80.

This stage is deliberately separate from the Docker-tested pipeline because it needs a GPU
stack (torch with Apple MPS or CUDA, transformers >= 5, pypdfium2) that is not in
requirements.txt. Run it natively in its own environment:

    python src/ocr_vlm.py                 # OCR every document marked ocr_server_used -> staging
    python src/ocr_vlm.py --apply         # copy staged text into data/final + update the manifest

Phase 1 never touches data/final. It caches every page in data/intermediate/ocr_vlm/, so a run
of several hours can be interrupted and resumed. Phase 2 (--apply) replaces each document's
Markdown and records ``ocr_engine`` and ``ocr_truncated_pages`` in the manifest.
"""

import argparse
import hashlib
import html
import json
import logging
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import MANIFEST_PATH

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STAGING_DIR = PROJECT_ROOT / "data" / "intermediate" / "ocr_vlm"
LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_MODEL = "lightonai/LightOnOCR-3-1B"
RENDER_DPI = 200
DEFAULT_MAX_NEW_TOKENS = 8192  # table pages are verbose; 3500 truncated a three-table page

TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


class _TableParser(HTMLParser):
    """Collect the rows of one HTML table as lists of cell strings."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _table_to_markdown(table_html: str) -> str:
    parser = _TableParser()
    parser.feed(table_html)
    rows = parser.rows
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    cell = lambda text: html.unescape(text).replace("|", "\\|")  # noqa: E731
    lines = ["| " + " | ".join(cell(c) for c in rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows[1:]]
    return "\n".join(lines)


def html_tables_to_markdown(text: str) -> str:
    """Replace every HTML <table> in OCR output with a compact Markdown table."""
    return TABLE_RE.sub(lambda m: "\n" + _table_to_markdown(m.group(0)) + "\n", text)


def ocr_document(page_count: int, recognize_page, cache_path: Path, logger: logging.Logger) -> tuple[str, list[int]]:
    """OCR a document page by page, resuming from ``cache_path``.

    ``recognize_page(index) -> (text, truncated)`` does the model work. Each finished page is
    written to the cache at once, so an interrupted run loses at most one page. Returns the
    document Markdown and the 1-based numbers of pages that hit the token cap."""
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for index in range(page_count):
        if str(index) in cache:
            continue
        text, truncated = recognize_page(index)
        cache[str(index)] = {"text": text, "truncated": truncated}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        logger.info("  page %d/%d done%s", index + 1, page_count, " (HIT TOKEN CAP)" if truncated else "")
    pages = [html_tables_to_markdown(cache[str(i)]["text"]).strip() for i in range(page_count)]
    truncated_pages = [i + 1 for i in range(page_count) if cache[str(i)]["truncated"]]
    return "\n\n".join(pages) + "\n", truncated_pages


def staged_paths(record: dict) -> tuple[Path, Path]:
    key = hashlib.sha1(f"{record['task_id']}|{record['pdf_url']}".encode()).hexdigest()
    return STAGING_DIR / f"{key}.md", STAGING_DIR / f"{key}.pages.json"


def load_manifest() -> list[dict]:
    return [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_manifest(records: list[dict]) -> None:
    MANIFEST_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def load_model(model_id: str):
    """Load the OCR model and return ``(recognize_image, device)``. Imports are local so the
    pure functions above stay importable (and testable in Docker) without a GPU stack."""
    import torch
    from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float32 if device == "mps" else torch.bfloat16
    model = LightOnOcrForConditionalGeneration.from_pretrained(model_id, dtype=dtype).to(device).eval()
    processor = LightOnOcrProcessor.from_pretrained(model_id)

    def recognize(image, max_new_tokens: int) -> tuple[str, bool]:
        conversation = [{"role": "user", "content": [{"type": "image", "image": image}]}]  # no text = transcription
        inputs = processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt"
        )
        inputs = {k: (v.to(device=device, dtype=dtype) if v.is_floating_point() else v.to(device)) for k, v in inputs.items()}
        with torch.no_grad():
            ids = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        generated = ids[0, inputs["input_ids"].shape[1]:]
        return processor.decode(generated, skip_special_tokens=True), len(generated) >= max_new_tokens

    return recognize, device


def run_ocr(args, logger: logging.Logger) -> None:
    import pypdfium2 as pdfium

    records = [r for r in load_manifest() if r.get("ocr_server_used")]
    if args.task_id:
        records = [r for r in records if r["task_id"] == args.task_id]
    if args.match:
        records = [r for r in records if args.match in r["pdf_path"]]
    if args.limit:
        records = records[: args.limit]
    logger.info("OCR with %s: %d document(s)", args.model, len(records))
    if args.dry_run:
        for r in records:
            logger.info("would OCR %s", r["pdf_path"])
        return
    recognize, device = load_model(args.model)
    logger.info("model loaded on %s", device)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (STAGING_DIR / "engine.txt").write_text(args.model, encoding="utf-8")  # read back by --apply
    for number, record in enumerate(records, 1):
        md_path, cache_path = staged_paths(record)
        if md_path.exists():
            continue
        pdf = pdfium.PdfDocument(str(PROJECT_ROOT / record["pdf_path"]))
        logger.info("[%d/%d] %s (%d pages)", number, len(records), record["pdf_path"], len(pdf))

        def recognize_page(index: int, pdf=pdf):
            image = pdf[index].render(scale=RENDER_DPI / 72).to_pil().convert("RGB")
            return recognize(image, args.max_new_tokens)

        text, truncated = ocr_document(len(pdf), recognize_page, cache_path, logger)
        md_path.write_text(text, encoding="utf-8")
        if truncated:
            logger.warning("%s: pages that hit the %d-token cap: %s", record["pdf_path"], args.max_new_tokens, truncated)


def apply_staged(logger: logging.Logger) -> None:
    """Replace each OCR'd document's Markdown with its staged VLM text and update the manifest."""
    records = load_manifest()
    engine_file = STAGING_DIR / "engine.txt"
    engine = engine_file.read_text(encoding="utf-8").strip() if engine_file.exists() else DEFAULT_MODEL
    applied = 0
    for record in records:
        if not record.get("ocr_server_used"):
            continue
        md_path, cache_path = staged_paths(record)
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        target = PROJECT_ROOT / record["markdown_path"]
        target.write_text(text, encoding="utf-8")
        record["ocr_engine"] = engine
        record["ocr_truncated_pages"] = [int(i) + 1 for i, page in sorted(cache.items(), key=lambda kv: int(kv[0])) if page["truncated"]]
        record["chars"] = len(text)
        if record.get("pages"):
            record["chars_per_page"] = round(len(text) / record["pages"], 1)
        applied += 1
    write_manifest(records)
    logger.info("applied staged OCR text to %d document(s)", applied)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-OCR scanned/garbled documents with a VLM OCR model.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--task-id", default=None, help="Only documents of this task.")
    parser.add_argument("--match", default=None, help="Only documents whose pdf_path contains this text.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many documents.")
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--dry-run", action="store_true", help="List the documents without running the model.")
    parser.add_argument("--apply", action="store_true", help="Copy staged text into data/final and update the manifest.")
    args = parser.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s ocr_vlm: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOGS_DIR / "ocr_vlm.log")])
    logger = logging.getLogger("ocr_vlm")
    if args.apply:
        apply_staged(logger)
    else:
        run_ocr(args, logger)


if __name__ == "__main__":
    main()
