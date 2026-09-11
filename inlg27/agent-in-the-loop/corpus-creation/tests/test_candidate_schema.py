from src.candidate_schema import candidate_issues, demote, slugify


def test_slugify_is_deterministic_and_filesystem_safe():
    assert slugify("Task 1: A/B & C") == "task-1-a-b-c"


def test_candidate_issues_accepts_a_minimal_candidate():
    candidate = {
        "task_id": "task-1",
        "venue": "SemEval",
        "parent_venue": "SemEval",
        "year": 2025,
        "task_name": "Task 1",
        "overview": {"pdf_url": "https://example.org/overview.pdf"},
        "participants": [{"pdf_url": "https://example.org/paper.pdf"}],
        "provenance": {"confidence": "high"},
    }
    assert candidate_issues(candidate) == []


def test_demote_preserves_existing_reasons_and_changes_high_to_medium():
    candidate = {"provenance": {"confidence": "high", "confidence_reasons": ["first"]}}
    demote(candidate, ["second", "first"])
    assert candidate["provenance"] == {
        "confidence": "medium",
        "confidence_reasons": ["first", "second"],
    }
