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


def extract_part_text(part: dict) -> str:
    tree = HTMLTree.parse(part.get("text", ""))
    return extract_plain_text(
        tree,
        main_content=False,
        preserve_formatting=True,
        links=False,
        comments=False,
    ).strip()


def write_document(output_file: TextIO, warc_record: WarcRecord, record_json: dict) -> None:
    doc_parts = record_json.get("docParts", {})
    long_part = doc_parts.get("L")
    short_part = doc_parts.get("K") or doc_parts.get("S")

    head_fields = extract_head_fields(
        (long_part or short_part or {}).get("head", "")
    )
    title = ((long_part or short_part or {}).get("documentTitle") or {}).get("title", "")
    abstract = extract_part_text(short_part) if short_part else None
    content = extract_part_text(long_part) if long_part else None

    output_file.write(
        json.dumps(
            {
                "doc_id": record_json.get("requestedDocumentId"),
                "url": warc_record.headers.get("WARC-Target-URI"),
                "language": "de",
                "document_type": head_fields.get("Dokumenttyp"),
                "court": head_fields.get("Gericht"),
                "decision_date": head_fields.get("Entscheidungsdatum"),
                "file_number": head_fields.get("Aktenzeichen"),
                "ecli": head_fields.get("ECLI"),
                "title": title,
                "abstract": abstract,
                "content": content,
                "text": "\n\n".join(
                    part for part in (title, abstract, content) if part
                ),
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def process_warc_files(input_paths: list[Path]) -> tuple[int, dict[str, int], int]:
    processed = 0
    written: dict[str, int] = {}
    skipped = 0
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
                        document_type = extract_head_fields(
                            next(iter(record_json.get("docParts", {}).values()), {}).get(
                                "head", ""
                            )
                        ).get("Dokumenttyp") or "unknown"
                    except (json.JSONDecodeError, UnicodeError, ValueError) as error:
                        skipped += 1
                        click.echo(
                            f"Skipping {warc_record.record_id}: {error}", err=True
                        )
                        continue

                    slug = slugify(document_type)
                    if slug not in outputs:
                        outputs[slug] = gzip.open(
                            f"documents-{slug}.jsonl.gz", "wt", encoding="utf-8"
                        )
                        written[slug] = 0

                    write_document(outputs[slug], warc_record, record_json)
                    written[slug] += 1

                    if processed % 1000 == 0:
                        click.echo(f"Processed {processed:,} documents", err=True)
    finally:
        for output_file in outputs.values():
            output_file.close()

    return processed, written, skipped


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

    processed, written, skipped = process_warc_files(input_paths)

    click.echo(
        f"Done: processed {processed:,} JSON documents from {len(input_paths):,} "
        f"files; skipped {skipped:,} invalid records.",
        err=True,
    )
    for slug, count in sorted(written.items(), key=lambda item: -item[1]):
        click.echo(f"{count:>6,}  documents-{slug}.jsonl.gz")


if __name__ == "__main__":
    main()
