#!/usr/bin/env python3

import json
import re
from enum import Enum
from pathlib import Path

import click


class SummaryMode(str, Enum):
    TITLE = "title"
    ABSTRACT = "abstract"
    TITLE_AND_ABSTRACT = "title-and-abstract"


def normalize_text(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"(?<=\w)-\s+(?=[a-z])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(markdown: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    if not match:
        raise ValueError("No level-one title found")
    return normalize_text(match.group(1))


def extract_abstract(markdown: str) -> str:
    lines = markdown.splitlines()
    abstract_lines: list[str] = []
    in_abstract = False

    for line in lines:
        if not in_abstract:
            match = re.match(
                r"^\s*(?:#{1,6}\s*)?(?:\*{1,2})?Abstract"
                r"(?:\*{1,2})?\s*(?:[.:]\s*)?(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                in_abstract = True
                abstract_lines.append(match.group(1))
            continue

        if re.match(r"^\s*#{1,6}\s+", line):
            break
        if re.match(r"^\s*(?:\*{0,2})?(?:Keywords|Copyright)\b", line):
            break
        abstract_lines.append(line)

    abstract = normalize_text("\n".join(abstract_lines))
    if not abstract:
        raise ValueError("No abstract found")
    return abstract


def create_summary(title: str, abstract: str, mode: SummaryMode) -> str:
    if mode is SummaryMode.TITLE:
        return title
    if mode is SummaryMode.ABSTRACT:
        return abstract
    return f"{title}\n\n{abstract}"


def find_papers(input_directory: Path) -> list[Path]:
    papers = sorted(input_directory.rglob("paper.md"))
    if not papers:
        raise ValueError(f"No paper.md files found in {input_directory}")

    ids = [paper.parent.name for paper in papers]
    if len(ids) != len(set(ids)):
        raise ValueError("Paper directory names must be unique")
    return papers


def generate_summaries(
    input_directory: Path, output_file: Path, mode: SummaryMode
) -> None:
    papers = find_papers(input_directory)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as output:
        for paper in papers:
            markdown = paper.read_text(encoding="utf-8")
            title = extract_title(markdown)
            abstract = extract_abstract(markdown)
            record = {
                "id": paper.parent.name,
                "summary": create_summary(title, abstract, mode),
            }
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


@click.command()
@click.option(
    "--input",
    "input_directory",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory containing paper directories with paper.md files.",
)
@click.option(
    "--output",
    "output_file",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Destination JSONL file.",
)
@click.option(
    "--summary",
    "summary_mode",
    required=True,
    type=click.Choice([mode.value for mode in SummaryMode]),
    help="Text used as each paper's summary.",
)
def main(input_directory: Path, output_file: Path, summary_mode: str) -> None:
    try:
        generate_summaries(
            input_directory, output_file, SummaryMode(summary_mode)
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    main()
