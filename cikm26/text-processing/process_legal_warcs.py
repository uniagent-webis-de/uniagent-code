#!/usr/bin/env python3

import gzip
import json
import re
from glob import glob
from pathlib import Path
from typing import TextIO

import click
from fastwarc.warc import ArchiveIterator, WarcRecord, WarcRecordType
from resiliparse.extract.html2text import extract_plain_text
from resiliparse.parse.html import HTMLTree

# hessenrecht renders "Redaktionelle Hinweise" (editorial notes) and
# "Permalink" boxes as trailing sections, always after the actual document
# text; whichever of these headings comes first marks where to cut them off.
_TRAILING_SECTION_PATTERN = re.compile(r"Redaktionelle Hinweise|Permalink")


def extract_head_fields(head_html: str) -> dict[str, str]:
    """Extract the label/value pairs (e.g. "Gericht", "Dokumenttyp") from a
    hessenrecht document part's head HTML table."""
    fields: dict[str, str] = {}
    if not head_html:
        return fields

    tree = HTMLTree.parse(head_html)
    for header_cell in tree.body.query_selector_all("th"):
        label = (header_cell.text or "").strip().removesuffix(":")
        if not label:
            continue

        value_cell = header_cell.parent.query_selector("td")
        if value_cell is not None and value_cell.text:
            fields[label] = value_cell.text.strip()

    return fields


def extract_content(text_html: str) -> str:
    """Extracts the plain-text content of a docPart's "text" HTML, with the
    trailing "Redaktionelle Hinweise"/"Permalink" boxes removed."""
    plain_text = extract_plain_text(text_html or "")
    match = _TRAILING_SECTION_PATTERN.search(plain_text)
    if match:
        plain_text = plain_text[: match.start()]
    return plain_text.strip()


def extract_metadata(warc_record: WarcRecord, record_json: dict) -> dict:
    """Extracts metadata, the raw title, and the plain-text content of one
    hessenrecht WARC record. The record's "defaultPart" -- the docPart
    hessenrecht itself considers the primary view for the requested document
    -- is used as the single source for all of these fields."""
    doc_parts = record_json.get("docParts", {})
    part = doc_parts.get(record_json.get("defaultPart"), {})
    head_fields = extract_head_fields(part.get("head", ""))
    title = (part.get("documentTitle") or {}).get("title", "")
    content = extract_content(part.get("text", ""))

    return {
        "doc_id": record_json.get("requestedDocumentId"),
        "url": warc_record.headers.get("WARC-Target-URI"),
        "document_type": head_fields.get("Dokumenttyp"),
        "court": head_fields.get("Gericht"),
        "decision_date": head_fields.get("Entscheidungsdatum"),
        "file_number": head_fields.get("Aktenzeichen"),
        "ecli": head_fields.get("ECLI"),
        "title": title,
        "content": content,
        "text": f"{title} {content}",
    }


def write_document(output_file: TextIO, document: dict) -> None:
    """Writes one already-extracted document as a JSON line."""
    output_file.write(json.dumps(document, ensure_ascii=False) + "\n")


def process_warc_files(input_paths: list[Path]) -> tuple[int, int, int]:
    """Processes all input_paths, writing extracted documents to
    legal-hessen-processed/documents.jsonl.gz, and the URL of every skipped
    record (invalid JSON, or missing title/content) to
    legal-hessen-processed/skipped-urls.txt, one per line.

    Returns (processed, written, skipped) counts.
    """
    processed = 0
    written = 0
    skipped = 0

    output_dir = Path("legal-hessen-processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    with gzip.open(
        output_dir / "documents.jsonl.gz", "wt", encoding="utf-8"
    ) as documents_file, (output_dir / "skipped-urls.txt").open(
        "w", encoding="utf-8"
    ) as skipped_urls_file:
        for input_path in input_paths:
            click.echo(f"Processing {input_path}", err=True)
            with input_path.open("rb") as warc_file:
                records = ArchiveIterator(
                    warc_file,
                    record_types=WarcRecordType.response,
                    parse_http=True,
                    auto_decode="all",
                )

                for warc_record in records:
                    if warc_record.http_content_type != "application/json":
                        continue

                    processed += 1
                    url = warc_record.headers.get("WARC-Target-URI")
                    try:
                        record_json = json.loads(warc_record.reader.read())
                        document = extract_metadata(warc_record, record_json)
                    except (json.JSONDecodeError, UnicodeError, ValueError) as error:
                        skipped += 1
                        skipped_urls_file.write(f"{url}\n")
                        click.echo(
                            f"Skipping {warc_record.record_id}: {error}", err=True
                        )
                        continue

                    if not document["title"] or not document["content"]:
                        skipped += 1
                        skipped_urls_file.write(f"{url}\n")
                        continue

                    write_document(documents_file, document)
                    written += 1

                    if processed % 1000 == 0:
                        click.echo(f"Processed {processed:,} documents", err=True)

    return processed, written, skipped


@click.command()
@click.argument("input_glob", default="legal-hessen/*.warc.gz")
def main(input_glob: str) -> None:
    """Extract legal documents from hessenrecht WARC files matching INPUT_GLOB,
    writing all of them to legal-hessen-processed/documents.jsonl.gz and the
    URLs of any skipped documents to legal-hessen-processed/skipped-urls.txt.

    Quote INPUT_GLOB to ensure it is expanded by this command instead of the shell.
    """
    input_paths = sorted(
        path for match in glob(input_glob, recursive=True) if (path := Path(match)).is_file()
    )
    if not input_paths:
        raise click.ClickException(f"No files match input glob: {input_glob}")

    processed, written, skipped = process_warc_files(input_paths)

    click.echo(
        f"Done: processed {processed:,} JSON documents from {len(input_paths):,} "
        f"files; wrote {written:,} documents; skipped {skipped:,} documents "
        "(invalid or missing title/content).",
        err=True,
    )


if __name__ == "__main__":
    main()

