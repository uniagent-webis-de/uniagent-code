import json
import tempfile
import unittest
from pathlib import Path

from business_trip_tools import (
    CheckFactsTool,
    ListCaseDocumentsTool,
    LookupPolicyTool,
    ReadPdfTool,
    SearchCaseTool,
)
from predict import input_cases, parse_decision


DATASET = (
    Path(__file__).parents[2] / "datasets" / "business-trip-spot-check" / "inputs"
).resolve()


class BaselineTest(unittest.TestCase):
    def test_lists_all_cases(self):
        self.assertEqual(
            input_cases(DATASET),
            [f"dienstreiseantrag-0{index}" for index in range(1, 6)],
        )

    def test_lists_and_reads_case_documents(self):
        case_id = "dienstreiseantrag-03"
        listed = json.loads(ListCaseDocumentsTool(DATASET, case_id)(case_id))
        self.assertEqual(3, len(listed))
        text = ReadPdfTool(DATASET, case_id)(case_id, "antrag-dienstreisegenehmigung.pdf")
        self.assertIn("Lyon, FRANKREICH", text)

    def test_rejects_cross_case_access(self):
        tool = ListCaseDocumentsTool(DATASET, "dienstreiseantrag-03")
        with self.assertRaises(ValueError):
            tool("dienstreiseantrag-04")

    def test_searches_with_citations(self):
        case_id = "dienstreiseantrag-05"
        matches = json.loads(SearchCaseTool(DATASET, case_id)(case_id, "Doppelfinanzierung", 5))
        self.assertTrue(matches)
        self.assertEqual("email-stipendienzusage.pdf", matches[0]["document"])

    def test_policy_lookup(self):
        result = json.loads(LookupPolicyTool()("Doppelfinanzierung Stipendium"))
        self.assertIn("double_funding", result["policies"])

    def test_deterministic_fact_checks(self):
        tool = CheckFactsTool()
        dates = json.loads(
            tool(
                {
                    "kind": "compare_dates",
                    "comparisons": [
                        {
                            "name": "application_before_trip",
                            "left": "20.10.2026",
                            "operator": "<",
                            "right": "14.10.2026",
                        }
                    ],
                }
            )
        )
        self.assertFalse(dates["results"][0]["passed"])

        overlap = json.loads(
            tool(
                {
                    "kind": "overlap",
                    "left": ["Flug", "Unterkunft"],
                    "right": ["Konferenz", "Flug"],
                }
            )
        )
        self.assertEqual(["flug"], overlap["overlap"])

    def test_parses_strict_decision(self):
        answer = json.dumps(
            {
                "antrag": "dienstreiseantrag-01",
                "result": "abgelehnt",
                "begruendung": "Der Antrag wurde nach Reisebeginn gestellt.",
            }
        )
        self.assertEqual("abgelehnt", parse_decision(answer, "dienstreiseantrag-01")["result"])

    def test_does_not_accept_malformed_decision(self):
        with self.assertRaises(ValueError):
            parse_decision("abgelehnt", "dienstreiseantrag-01")


if __name__ == "__main__":
    unittest.main()
