from src.corpus_corrections import apply_metadata_corrections, correct_fulltext


def test_corrections_match_task_and_pdf_and_preserve_other_documents():
    task = {"task_id": "task", "overview": {"pdf_url": "overview"},
            "participants": [{"pdf_url": "paper", "team_name": None}, {"pdf_url": "other"}]}
    apply_metadata_corrections(task, {"documents": {"task|paper": {
        "team_name": "Team A", "team_name_source": {"kind": "organizer_roster"},
        "task_numbers": [1]}}, "tasks": {"task": {
        "subtasks": [{"number": 1, "name": "Data-to-text"}]}}})
    assert task["participants"][0]["team_name"] == "Team A"
    assert task["participants"][0]["task_numbers"] == [1]
    assert task["participants"][1] == {"pdf_url": "other"}
    assert task["source"]["subtasks"] == [{"number": 1, "name": "Data-to-text"}]
    assert task["overview"]["is_umbrella"] is True


def test_fulltext_correction_is_repeatable_and_refuses_changed_source():
    import pytest
    edits = {"task|paper": [{"before": "wrong order", "after": "right order"}]}
    assert correct_fulltext("task", "paper", "wrong order", edits) == "right order"
    assert correct_fulltext("task", "paper", "right order", edits) == "right order"
    with pytest.raises(ValueError, match="source changed"):
        correct_fulltext("task", "paper", "unrelated text", edits)
    assert correct_fulltext("other", "paper", "wrong order", edits) == "wrong order"


def test_reviewed_automin_edit_preserves_words_and_section_order():
    import json
    import re
    from collections import Counter
    from pathlib import Path

    edits = json.loads((Path(__file__).parents[1] / "curation/fulltext_corrections.json").read_text())
    key = "inlg2023-automatic-minuting-automin|https://aclanthology.org/2023.inlg-genchal.15.pdf"
    original = edits[key][0]["before"]
    fixed = correct_fulltext(*key.split("|"), original, edits)
    headings = ["## 4 System Overview", "### 4.1", "### 4.2", "### 4.3", "### 4.4", "## 5 Results"]
    assert [fixed.index(h) for h in headings] == sorted(fixed.index(h) for h in headings)
    assert Counter(re.findall(r"\S+", fixed)) == Counter(re.findall(r"\S+", original))
    assert correct_fulltext(*key.split("|"), fixed, edits) == fixed


def test_gem_table8_recovers_every_system_and_metric_cell():
    import json
    from pathlib import Path

    edits = json.loads((Path(__file__).parents[1] / "curation/fulltext_corrections.json").read_text())
    key = "inlg2024-gem-multilingual-data-to-text-and-summarization|https://aclanthology.org/2024.inlg-genchal.2.pdf"
    table = edits[key][2]["after"]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    assert len(rows) == 29  # header and seven systems for each of four metrics
    assert all(len(row.split("|")) == 10 for row in rows)
    assert "| BLEU ↑ | DCU-NLG-PBN | 29.08 | 25.2 | 26.02 | 23.96 | 30.34 | 20.46 |" in rows
    assert "| BERT F1 ↑ | SaarLST | 0.931 | 0.921 | 0.917 | 0.934 | 0.929 | 0.919 |" in rows
    assert table.count("n/a") == 12
    for edit in edits[key]:
        # Each independently anchored edit accepts both raw and corrected text.
        single = {key: [edit]}
        fixed = correct_fulltext(*key.split("|"), edit["before"], single)
        assert correct_fulltext(*key.split("|"), fixed, single) == fixed


def test_reviewed_column_repairs_preserve_all_words_and_images():
    import json
    import re
    from collections import Counter
    from pathlib import Path

    edits = json.loads((Path(__file__).parents[1] / "curation/fulltext_corrections.json").read_text())
    key = next((key for key in edits if key.endswith("|https://ceur-ws.org/Vol-1737/T7-2.pdf")), None)
    assert key is not None
    fixed = edits[key][0]["after"]
    assert fixed.index("## 4.") < fixed.index("## 5.") < fixed.index("## 6.")
    for key, changes in edits.items():
        for change in changes:
            if change.get("reason", "").startswith("Restore PDF column order"):
                before, after = change["before"], change["after"]
                assert Counter(re.findall(r"\S+", before)) == Counter(re.findall(r"\S+", after))
                assert re.findall(r"!\[[^]]*\]\([^)]*\)", before) == re.findall(r"!\[[^]]*\]\([^)]*\)", after)
                assert correct_fulltext(*key.split("|"), after, {key: [change]}) == after


def test_corrected_dataset_footnotes_keep_their_hyphens_and_kind():
    from src.paper_links import document_links

    urls = ["https://github.com/google-research-datasets/gap-coreference",
            "https://github.com/headacheboy/data-of-multimodal-sarcasm-detection",
            "https://github.com/monkeylearn/sentiment-analysis-benchmark",
            "https://github.com/ajb129/tscorpus"]
    assert [link["kind"] for link in document_links("\n".join(urls))] == ["dataset"] * 4
