import logging
from pathlib import Path

from src.collect_sisap import (
    build_task_candidate,
    _paper_record,
    parse_2025_results,
    parse_2026_teams,
    parse_registration_issues,
    parse_springer_indexing_challenge,
    parse_task_page,
)
from src.sisap_config import SISAP_EDITIONS, selected_editions


LOGGER = logging.getLogger("test_sisap")


def test_config_covers_all_four_editions_and_eleven_task_units():
    assert [edition["year"] for edition in SISAP_EDITIONS] == [2023, 2024, 2025, 2026]
    assert sum(len(edition["tasks"]) for edition in SISAP_EDITIONS) == 11
    assert selected_editions(2025)[0]["collection_id"] == "sisap2025"
    assert selected_editions(1900) == []


def test_parse_task_page_preserves_official_headings_and_description():
    raw = """
    <html><body>
      <h1>Tasks</h1>
      <h2>Task 1: Unrestricted Indexing</h2>
      <p>Build an index under the challenge rules.</p>
      <h2>Task 2: Memory-Constrained Indexing with Reranking</h2>
      <p>Use a memory-constrained pipeline.</p>
    </body></html>
    """
    tasks = [
        {"number": 1, "short_name": "Task 1", "name": "Unrestricted Indexing"},
        {"number": 2, "short_name": "Task 2", "name": "Memory-Constrained Indexing with Reranking"},
    ]
    parsed = parse_task_page(raw, tasks)
    assert parsed["1"]["found"] is True
    assert parsed["1"]["official_heading"] == "Task 1: Unrestricted Indexing"
    assert "Build an index" in parsed["1"]["description"]
    assert parsed["2"]["found"] is True


def test_parse_springer_indexing_challenge_extracts_roles_dois_and_authors():
    raw = """
    <h3>Indexing Challenge</h3>
    <ol>
      <li data-test="chapter">
        <h4 data-test="front-matter">Front Matter</h4>
      </li>
      <li data-test="chapter">
        <h4 data-test="chapter-title-Overview"><a href="/chapter/10.1007/978-3-031-00000-0_21">Overview of the SISAP 2025 Indexing Challenge</a></h4>
        <ul class="app-author-list"><li>A. Organizer, B. Organizer</li></ul>
      </li>
      <li data-test="chapter">
        <h4 data-test="chapter-title-System"><a href="/chapter/10.1007/978-3-031-00000-0_22">A Participant System</a></h4>
        <ul class="app-author-list"><li>Participant One, Participant Two</li></ul>
        <span data-test="page-number">Pages 10-20</span>
      </li>
    </ol>
    <h3>Back Matter</h3>
    """
    papers = parse_springer_indexing_challenge(raw, "https://link.springer.com/book/")
    assert [paper["role"] for paper in papers] == ["overview", "participant"]
    assert papers[1]["doi"] == "10.1007/978-3-031-00000-0_22"
    assert papers[1]["pdf_url"].endswith("978-3-031-00000-0_22.pdf")
    assert papers[1]["authors"] == ["Participant One, Participant Two"]


def test_parse_2025_results_preserves_paper_repo_and_task_assignments():
    raw = """
    <table>
      <tr><th>Team</th><th>Members</th><th>Task</th><th>Paper</th><th>Repo</th></tr>
      <tr><td>Team A</td><td>A. Author</td><td>1, 2</td>
        <td><a href="https://link.springer.com/chapter/10.1007/978-3-032-06069-3_38">System paper</a></td>
        <td><a href="https://github.com/example/team-a">repo</a></td></tr>
      <tr><td>BL-SearchGraph</td><td>Organizers</td><td>1</td><td>—</td><td>—</td></tr>
    </table>
    <table>
      <tr><th>Team</th><th>Recall</th></tr>
      <tr><td>Team A</td><td>0.81</td></tr>
    </table>
    """
    participants, result_tables = parse_2025_results(raw)
    assert participants[0]["task_numbers"] == [1, 2]
    assert participants[0]["pdf_url"].endswith("978-3-032-06069-3_38.pdf")
    assert participants[0]["code_urls"] == ["https://github.com/example/team-a"]
    assert result_tables["1"] == [{"Team": "Team A", "Recall": "0.81"}]


def test_parse_2024_registration_archive_extracts_explicit_task_sets():
    raw = '[{"body":"### team\\n\\nHIOB\\n\\n### tasks\\n\\n1, 2, and 3"}]'
    assert parse_registration_issues(raw) == {"HIOB": {1, 2, 3}}


def test_parse_2026_leaderboard_json_with_trailing_commas_excludes_baseline():
    raw = '{"Organizers":{"is-baseline":true},"team-a":{"paper":43,"submissions":[{"tasks":["task1"]}],},}'
    parsed = parse_2026_teams(raw)
    assert list(parsed) == ["team-a"]
    assert parsed["team-a"]["paper"] == 43


def test_sisap_candidate_marks_shared_documents_and_review_reasons():
    edition = {
        "year": 2025,
        "collection_id": "sisap2025",
        "official_url": "https://example.org/sisap2025",
        "tasks_url": "https://example.org/tasks",
        "tira_url": "https://www.tira.io/tasks",
    }
    task = {"number": 1, "name": "Resource-limited indexing", "short_name": "Task 1"}
    overview = {
        "title": "Overview",
        "authors": [],
        "paper_url": "https://example.org/overview",
        "pdf_url": "https://example.org/overview.pdf",
        "source_id": "overview",
        "role": "overview",
    }
    participants = [
        {"title": "Paper 1", "authors": [], "paper_url": "https://example.org/1", "pdf_url": "https://example.org/1.pdf", "source_id": "1", "team_name": "A", "task_numbers": [1]},
        {"title": "Paper 2", "authors": [], "paper_url": "https://example.org/2", "pdf_url": "https://example.org/2.pdf", "source_id": "2", "team_name": "B", "task_numbers": [1]},
    ]
    candidate = build_task_candidate(edition, task, {"found": True}, overview, participants, [{"Recall": "0.8"}], LOGGER)
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["overview"]["shared_document_id"] == "sisap2025:overview"
    assert all(p["shared_document_group"] == "sisap2025" for p in candidate["participants"])


def test_sisap_uses_verified_open_access_pdf_fallback_but_keeps_publisher_identity():
    edition = next(edition for edition in SISAP_EDITIONS if edition["year"] == 2023)
    paper = {
        "title": "General and Practical Tuning Method",
        "authors": [],
        "paper_url": "https://link.springer.com/chapter/10.1007/978-3-031-46994-7_23",
        "pdf_url": "https://link.springer.com/content/pdf/10.1007/978-3-031-46994-7_23.pdf",
        "doi": "10.1007/978-3-031-46994-7_23",
        "source_id": "10.1007_978-3-031-46994-7_23",
        "role": "participant",
    }
    record = _paper_record(paper, edition, "Task A")
    assert record["pdf_url"] == "https://arxiv.org/pdf/2309.00472"
    assert record["publisher_pdf_url"].endswith("978-3-031-46994-7_23.pdf")
    assert record["pdf_source"] == "open_access_fallback"
