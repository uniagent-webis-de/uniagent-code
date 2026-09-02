import json
from pathlib import Path

from approvaltests import verify_as_json
from fastwarc.warc import ArchiveIterator, WarcRecordType

from process_legal_warcs import extract_metadata

RESOURCES_DIR = Path(__file__).parent / "resources"


def extract_documents(warc_path: Path) -> list[dict]:
    """Runs extract_metadata() on every JSON response record in warc_path and
    returns the resulting documents in the order they appear in the file."""
    documents = []
    with warc_path.open("rb") as warc_file:
        for warc_record in ArchiveIterator(
            warc_file,
            record_types=WarcRecordType.response,
            parse_http=True,
            auto_decode="all",
        ):
            if warc_record.http_content_type != "application/json":
                continue

            record_json = json.loads(warc_record.reader.read())
            documents.append(extract_metadata(warc_record, record_json))

    return documents


def verify_documents(warc_path: Path) -> None:
    """Extracts documents from warc_path, checks that "text" is exactly
    "title" + " " + "content" for each of them (so this derived field does not
    need to be approved itself), and approves the remaining fields."""
    documents = extract_documents(warc_path)
    for document in documents:
        assert document["text"] == f"{document['title']} {document['content']}"

    verify_as_json(
        [{key: value for key, value in document.items() if key != "text"} for document in documents]
    )


def test_metadata_example_01() -> None:
    verify_documents(RESOURCES_DIR / "example-01.warc.gz")


def test_metadata_example_02() -> None:
    verify_documents(RESOURCES_DIR / "example-02.warc.gz")


def test_metadata_example_03() -> None:
    verify_documents(RESOURCES_DIR / "example-03.warc.gz")


def test_metadata_example_04() -> None:
    verify_documents(RESOURCES_DIR / "example-04.warc.gz")


def test_metadata_example_05() -> None:
    verify_documents(RESOURCES_DIR / "example-05.warc.gz")


def test_metadata_example_06() -> None:
    verify_documents(RESOURCES_DIR / "example-06.warc.gz")
