#!/usr/bin/env python3
"""Extracts a single WARC record identified by its WARC-Target-URI from the
full hessenrecht crawl into a small, self-contained WARC file that can be used
as a test fixture (e.g. in tests/resources/).

Usage (from the text-processing/ directory):

    python3 tests/extract_test_warc.py <URL> <output-file> [--input-glob GLOB]

Example:

    python3 tests/extract_test_warc.py \\
        https://www.rv.hessenrecht.hessen.de/bshe/document/jlr-NNLHE0000506D \\
        tests/resources/gesetz_case_overview.warc.gz

It requires the full crawl (default: legal-hessen/*.warc.gz) to be present
locally; the extracted fixture is self-contained and does not require the
full crawl to be used afterwards.
"""

import gzip
from glob import glob
from pathlib import Path

import click
from fastwarc.warc import ArchiveIterator, WarcRecordType


@click.command()
@click.argument("url")
@click.argument("output_file", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--input-glob",
    default="legal-hessen/*.warc.gz",
    show_default=True,
    help="Glob matching the source WARC files to search.",
)
def extract(url: str, output_file: Path, input_glob: str) -> None:
    """Extracts the WARC record whose WARC-Target-URI equals URL into
    OUTPUT_FILE."""
    for input_path in sorted(glob(input_glob)):
        with open(input_path, "rb") as warc_file:
            for warc_record in ArchiveIterator(
                warc_file,
                record_types=WarcRecordType.response,
                parse_http=True,
                auto_decode="all",
            ):
                if warc_record.headers.get("WARC-Target-URI") != url:
                    continue

                # The body has to be read (and set back) once so it is
                # available again when the record is re-serialized below.
                warc_record.set_bytes_content(warc_record.reader.read())

                output_file.parent.mkdir(parents=True, exist_ok=True)
                open_output = gzip.open if output_file.suffix == ".gz" else open
                with open_output(output_file, "wb") as out:
                    warc_record.write(out, checksum_data=True)

                click.echo(f"Wrote {output_file} from {input_path}")
                return

    raise click.ClickException(f"No record found with WARC-Target-URI: {url}")


if __name__ == "__main__":
    extract()
