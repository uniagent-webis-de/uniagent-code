import json

from click.testing import CliRunner

from baseline import (
    SummaryMode,
    create_summary,
    extract_abstract,
    extract_title,
    main,
)


def test_extracts_title_and_heading_abstract():
    markdown = """# Paper Title

Author

### Abstract This is a hyphen-
ated abstract.

## 1 Introduction

Not part of the abstract.
"""

    assert extract_title(markdown) == "Paper Title"
    assert extract_abstract(markdown) == "This is a hyphenated abstract."


def test_extracts_plain_and_bold_abstracts():
    plain = """# First

Abstract. First paragraph.

Second paragraph.

Keywords: example
"""
    bold = """# Second

**Abstract A bold abstract**

## Introduction
"""

    assert extract_abstract(plain) == "First paragraph. Second paragraph."
    assert extract_abstract(bold) == "A bold abstract"


def test_summary_modes():
    assert create_summary("Title", "Abstract", SummaryMode.TITLE) == "Title"
    assert create_summary("Title", "Abstract", SummaryMode.ABSTRACT) == "Abstract"
    assert (
        create_summary("Title", "Abstract", SummaryMode.TITLE_AND_ABSTRACT)
        == "Title\n\nAbstract"
    )


def test_cli_writes_jsonl(tmp_path):
    input_directory = tmp_path / "papers"
    paper_directory = input_directory / "172"
    paper_directory.mkdir(parents=True)
    (paper_directory / "paper.txt.md").write_text(
        "# Paper Title\n\n### Abstract Paper abstract.\n\n## Introduction\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "output" / "summaries.jsonl"

    result = CliRunner().invoke(
        main,
        [
            "--input",
            str(input_directory),
            "--output",
            str(output_file),
            "--summary",
            "abstract",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "id": "172",
        "summary": "Paper abstract.",
    }
