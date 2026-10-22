import logging
from pathlib import Path

from src.collect_sisap import (
    build_edition_candidate,
    parse_2025_results,
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
    # 2025 titles the part "SISAP Indexing Challenge".
    renamed = raw.replace("<h3>Indexing Challenge</h3>", "<h3>SISAP Indexing Challenge</h3>")
    assert len(parse_springer_indexing_challenge(renamed, "https://link.springer.com/book/")) == 2


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


def test_configured_papers_map_to_real_subtasks_of_their_edition():
    for edition in SISAP_EDITIONS:
        subtasks = {task["number"] for task in edition["tasks"]}
        assert len(edition["papers"]) >= 2, edition["year"]
        for doi, mapping in edition["papers"].items():
            assert doi.startswith("10.1007/"), doi
            assert mapping["team"], doi
            assert mapping["tasks"] and set(mapping["tasks"]) <= subtasks, doi


def _paper(number: int, team: str | None, tasks: list[int]) -> dict:
    return {
        "title": f"Paper {number}",
        "authors": [],
        "paper_url": f"https://example.org/{number}",
        "pdf_url": f"https://example.org/{number}.pdf",
        "doi": f"10.1007/x_{number}",
        "source_id": str(number),
        "role": "participant",
        "team_name": team,
        "task_numbers": tasks,
    }


def test_edition_becomes_one_umbrella_task_keeping_each_papers_subtasks():
    edition = {
        "year": 2025,
        "collection_id": "sisap2025",
        "official_url": "https://example.org/sisap2025",
        "tira_url": "https://www.tira.io/tasks",
    }
    subtasks = [
        {"number": 1, "name": "One", "task_metadata": {"found": True}, "result_records": [{"Recall": "0.8"}]},
        {"number": 2, "name": "Two", "task_metadata": {"found": True}, "result_records": []},
    ]
    overview = {"title": "Overview", "paper_url": "https://example.org/ov", "pdf_url": "https://example.org/ov.pdf", "source_id": "ov", "role": "overview"}
    candidate = build_edition_candidate(edition, subtasks, overview, [_paper(1, "A", [1, 2]), _paper(2, "B", [2])], [], LOGGER)
    assert candidate["task_id"] == "sisap2025-indexing-challenge"
    assert candidate["provenance"]["confidence"] == "high"
    assert candidate["ceur_volume"] is None
    assert candidate["overview"]["is_umbrella"] is True
    assert [p["task_numbers"] for p in candidate["participants"]] == [[1, 2], [2]]
    assert [s["number"] for s in candidate["source"]["subtasks"]] == [1, 2]

    unmapped = build_edition_candidate(edition, subtasks, overview, [_paper(1, "A", [1]), _paper(2, None, [])], [], LOGGER)
    assert unmapped["provenance"]["confidence"] == "medium"
    assert any("10.1007/x_2" in reason for reason in unmapped["provenance"]["confidence_reasons"])
