import io
import json
import unittest
from unittest.mock import Mock

from process_warc import write_document


class WriteDocumentTest(unittest.TestCase):
    def test_writes_ir_datasets_compatible_document(self) -> None:
        output = io.StringIO()
        warc_record = Mock()
        warc_record.record_id = "<urn:uuid:document-id>"
        warc_record.headers.get.return_value = "https://example.com/document"

        write_document(
            output,
            warc_record,
            "Document title",
            "Document content",
            "en",
        )

        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "doc_id": "document-id",
                "url": "https://example.com/document",
                "language": "en",
                "title": "Document title",
                "content": "Document content",
                "text": "Document title\n\nDocument content",
            },
        )

    def test_text_omits_separator_when_title_is_empty(self) -> None:
        output = io.StringIO()
        warc_record = Mock()
        warc_record.record_id = "<urn:uuid:document-id>"
        warc_record.headers.get.return_value = None

        write_document(output, warc_record, "", "Document content", "en")

        self.assertEqual(json.loads(output.getvalue())["text"], "Document content")


if __name__ == "__main__":
    unittest.main()
