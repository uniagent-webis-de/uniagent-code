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

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "unknown"


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


def extract_metadata(warc_record: WarcRecord, record_json: dict) -> dict:
    """Extracts metadata, the raw title, and the plain-text content of one
    hessenrecht WARC record. The record's "defaultPart" -- the docPart
    hessenrecht itself considers the primary view for the requested document
    -- is used as the single source for all of these fields."""
    doc_parts = record_json.get("docParts", {})
    part = doc_parts.get(record_json.get("defaultPart"), {})
    head_fields = extract_head_fields(part.get("head", ""))

    return {
        "doc_id": record_json.get("requestedDocumentId"),
        "url": warc_record.headers.get("WARC-Target-URI"),
        "document_type": head_fields.get("Dokumenttyp"),
        "court": head_fields.get("Gericht"),
        "decision_date": head_fields.get("Entscheidungsdatum"),
        "file_number": head_fields.get("Aktenzeichen"),
        "ecli": head_fields.get("ECLI"),
        "title": (part.get("documentTitle") or {}).get("title", ""),
        "content": extract_plain_text(part.get("text") or ""),
    }


def write_document(output_file: TextIO, document: dict) -> bool:
    """Writes one already-extracted document as a JSON line. Returns True if
    its title is empty."""
    output_file.write(json.dumps(document, ensure_ascii=False) + "\n")
    return not document["title"]


def process_warc_files(input_paths: list[Path]) -> tuple[int, dict[str, int], int, int]:
    processed = 0
    written: dict[str, int] = {}
    skipped = 0
    empty = 0
    outputs: dict[str, TextIO] = {}

    try:
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
                    try:
                        record_json = json.loads(warc_record.reader.read())
                        document = extract_metadata(warc_record, record_json)
                    except (json.JSONDecodeError, UnicodeError, ValueError) as error:
                        skipped += 1
                        click.echo(
                            f"Skipping {warc_record.record_id}: {error}", err=True
                        )
                        continue

                    slug = slugify(document["document_type"] or "unknown")
                    if slug not in outputs:
                        outputs[slug] = gzip.open(
                            f"legal-hessen-processed/documents-{slug}.jsonl.gz", "wt", encoding="utf-8"
                        )
                        written[slug] = 0

                    if write_document(outputs[slug], document):
                        empty += 1
                    written[slug] += 1

                    if processed % 1000 == 0:
                        click.echo(f"Processed {processed:,} documents", err=True)
    finally:
        for output_file in outputs.values():
            output_file.close()

    return processed, written, skipped, empty


@click.command()
@click.argument("input_glob", default="legal-hessen/*.warc.gz")
def main(input_glob: str) -> None:
    """Extract legal documents from hessenrecht WARC files matching INPUT_GLOB,
    writing one documents-<type>.jsonl.gz file per document type.

    Quote INPUT_GLOB to ensure it is expanded by this command instead of the shell.
    """
    input_paths = sorted(
        path for match in glob(input_glob, recursive=True) if (path := Path(match)).is_file()
    )
    if not input_paths:
        raise click.ClickException(f"No files match input glob: {input_glob}")

    processed, written, skipped, empty = process_warc_files(input_paths)

    click.echo(
        f"Done: processed {processed:,} JSON documents from {len(input_paths):,} "
        f"files; skipped {skipped:,} invalid records; {empty:,} documents with empty title.",
        err=True,
    )
    for slug, count in sorted(written.items(), key=lambda item: -item[1]):
        click.echo(f"{count:>6,}  documents-{slug}.jsonl.gz")


if __name__ == "__main__":
    main()

