#!/usr/bin/env python3

import gzip
import json
from glob import glob
from pathlib import Path
from typing import TextIO

import click
from fastwarc.warc import ArchiveIterator, WarcRecord, WarcRecordType
from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException
from resiliparse.extract.html2text import extract_plain_text
from resiliparse.parse.html import HTMLTree

DetectorFactory.seed = 0


def detect_language(content: str) -> str | None:
    if not content:
        return None

    try:
        return detect(content[:10_000])
    except LangDetectException:
        return None


def write_document(
    output_file: TextIO,
    warc_record: WarcRecord,
    title: str,
    content: str,
    language: str,
) -> None:
    output_file.write(
        json.dumps(
            {
                "id": warc_record.record_id.removeprefix(
                    "<urn:uuid:"
                ).removesuffix(">"),
                "url": warc_record.headers.get("WARC-Target-URI"),
                "language": language,
                "title": title,
                "content": content,
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def process_warc_files(input_paths: list[Path]) -> tuple[int, dict[str, int], int, int]:
    processed = 0
    written = {"de": 0, "en": 0}
    excluded = 0
    failed = 0

    with gzip.open(
        "documents-de.jsonl.gz", "wt", encoding="utf-8"
    ) as german_output, gzip.open(
        "documents-en.jsonl.gz", "wt", encoding="utf-8"
    ) as english_output:
        outputs = {"de": german_output, "en": english_output}

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
                    processed += 1
                    if warc_record.http_content_type != "text/html":
                        continue

                    try:
                        tree = HTMLTree.parse_from_bytes(
                            warc_record.reader.read(),
                            encoding=warc_record.http_charset or "utf-8",
                        )
                        content = extract_plain_text(
                            tree,
                            main_content=True,
                            preserve_formatting=True,
                            links=False,
                            comments=False,
                        ).strip()
                        language = detect_language(content)
                        if language not in outputs:
                            excluded += 1
                            continue

                        write_document(
                            outputs[language],
                            warc_record,
                            (tree.title or "").strip(),
                            content,
                            language,
                        )
                        written[language] += 1
                    except (LookupError, UnicodeError, ValueError) as error:
                        failed += 1
                        click.echo(
                            f"Skipping {warc_record.record_id}: {error}", err=True
                        )

                    if processed % 1000 == 0:
                        click.echo(
                            f"Processed {processed:,} responses; wrote "
                            f"{written['de']:,} German and {written['en']:,} English "
                            "records",
                            err=True,
                        )

    return processed, written, excluded, failed


@click.command()
@click.argument("input_glob", default="*.warc.gz")
def main(input_glob: str) -> None:
    """Extract documents from WARC files matching INPUT_GLOB.

    Quote INPUT_GLOB to ensure it is expanded by this command instead of the shell.
    """
    input_paths = sorted(
        path for match in glob(input_glob, recursive=True) if (path := Path(match)).is_file()
    )
    if not input_paths:
        raise click.ClickException(f"No files match input glob: {input_glob}")

    processed, written, excluded, failed = process_warc_files(input_paths)
    click.echo(
        f"Done: processed {processed:,} responses from {len(input_paths):,} files; "
        f"wrote {written['de']:,} records to documents-de.jsonl.gz and "
        f"{written['en']:,} records to documents-en.jsonl.gz; excluded "
        f"{excluded:,} other-language records and skipped {failed:,} invalid HTML "
        "records.",
        err=True,
    )


if __name__ == "__main__":
    main()
