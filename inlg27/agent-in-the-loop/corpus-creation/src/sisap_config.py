"""Official SISAP Indexing Challenge editions and source URLs.

The challenge website is the authority for task definitions and the SISAP
proceedings are the authority for published organizer and participant papers.
GitHub/TIRA/DBLP sources below are supplemental evidence and statistics; they
must not create a participant paper without a corresponding published paper.

Each edition becomes one corpus task: its single organizer overview covers all
sub-tasks.  ``papers`` maps every participant chapter DOI to its team and the
sub-tasks it addressed, as stated in that edition's overview paper.
"""

from __future__ import annotations


SISAP_EDITIONS = [
    {
        "parent_venue": "SISAP",
        "year": 2023,
        "collection_id": "sisap2023",
        "official_url": "https://sisap-challenges.github.io/2023/",
        "tasks_url": "https://sisap-challenges.github.io/2023/tasks/",
        "methodology_url": "https://sisap-challenges.github.io/2023/evaluationmethodology/",
        "proceedings_url": "https://link.springer.com/book/10.1007/978-3-031-46994-7?page=2",
        "conference_url": "https://sisap.org/2023/program.html",
        "overview_url": "https://link.springer.com/chapter/10.1007/978-3-031-46994-7_21",
        "github_repo_url": "https://github.com/sisap-challenges/challenge2023",
        "github_files": {
            "preliminary_results": "https://raw.githubusercontent.com/sisap-challenges/challenge2023/main/results/RESULTS.md",
            "result_csv": "https://raw.githubusercontent.com/sisap-challenges/challenge2023/main/results/res.csv",
        },
        "dblp_url": "https://dblp.org/db/conf/sisap/sisap2023.html",
        "tira_url": "https://www.tira.io/tasks",
        "tasks": [
            {
                "number": "A",
                "slug": "task-a",
                "name": "Indexing and searching a LAION-5B deep features subset",
                "short_name": "Task A",
            },
            {
                "number": "B",
                "slug": "task-b",
                "name": "Binary sketches",
                "short_name": "Task B",
            },
            {
                "number": "C",
                "slug": "task-c",
                "name": "Indexing and searching on binary sketches",
                "short_name": "Task C",
            },
        ],
        # Overview Sect. 4.2.  HIOB (Tasks A-C) has no paper in the proceedings.
        "papers": {
            "10.1007/978-3-031-46994-7_22": {"team": "SWANN", "tasks": ["C"]},
            "10.1007/978-3-031-46994-7_23": {"team": "UTokyo", "tasks": ["A"]},
            "10.1007/978-3-031-46994-7_24": {"team": "LMI", "tasks": ["A"]},
            "10.1007/978-3-031-46994-7_25": {"team": "HSP", "tasks": ["A"]},
            "10.1007/978-3-031-46994-7_26": {"team": "CRANBERRY", "tasks": ["A"]},
        },
    },
    {
        "parent_venue": "SISAP",
        "year": 2024,
        "collection_id": "sisap2024",
        "official_url": "https://sisap-challenges.github.io/2024/",
        "tasks_url": "https://sisap-challenges.github.io/2024/tasks/",
        "methodology_url": "https://sisap-challenges.github.io/2024/evaluationmethodology/",
        "proceedings_url": "https://link.springer.com/book/10.1007/978-3-031-75823-2?page=2",
        "conference_url": "https://sisap.org/2024/program.html",
        "overview_url": "https://link.springer.com/chapter/10.1007/978-3-031-75823-2_21",
        "github_repo_url": "https://github.com/sisap-challenges/challenge2024",
        "github_files": {
            "task1_results": "https://raw.githubusercontent.com/sisap-challenges/challenge2024/main/sisap24-task1.csv",
            "task2_results": "https://raw.githubusercontent.com/sisap-challenges/challenge2024/main/sisap24-task2.csv",
            "task3_results": "https://raw.githubusercontent.com/sisap-challenges/challenge2024/main/sisap24-task3.csv",
            "results_discussion": "https://api.github.com/repos/sisap-challenges/challenge2024/discussions/8",
        },
        "dblp_url": "https://dblp.org/db/conf/sisap/sisap2024.html",
        "tira_url": "https://www.tira.io/tasks",
        "tasks": [
            {
                "number": 1,
                "slug": "task-1",
                "name": "Unrestricted Indexing",
                "short_name": "Task 1",
            },
            {
                "number": 2,
                "slug": "task-2",
                "name": "Memory-Constrained Indexing with Reranking",
                "short_name": "Task 2",
            },
            {
                "number": 3,
                "slug": "task-3",
                "name": "Memory-Constrained Indexing without Reranking",
                "short_name": "Task 3",
            },
        ],
        # Overview Sect. 3.2: DEGLIB and LMI solved Tasks 1 and 3 (LMI's Task 2
        # run was terminated after 24 h), HIOB all three, HSP Task 1.
        "papers": {
            "10.1007/978-3-031-75823-2_22": {"team": "LMI", "tasks": [1, 3]},
            "10.1007/978-3-031-75823-2_23": {"team": "HIOB", "tasks": [1, 2, 3]},
            "10.1007/978-3-031-75823-2_24": {"team": "DEGLIB", "tasks": [1, 3]},
            "10.1007/978-3-031-75823-2_25": {"team": "HSP", "tasks": [1]},
        },
    },
    {
        "parent_venue": "SISAP",
        "year": 2025,
        "collection_id": "sisap2025",
        "official_url": "https://sisap-challenges.github.io/2025/",
        "tasks_url": "https://sisap-challenges.github.io/2025/",
        "evaluation_url": "https://sisap-challenges.github.io/2025/evaluation/",
        "proceedings_url": "https://link.springer.com/book/10.1007/978-3-032-06069-3?page=3",
        "conference_url": "https://sisap.org/2025/program.html",
        "overview_url": "https://link.springer.com/chapter/10.1007/978-3-032-06069-3_33",
        "github_repo_url": "https://github.com/sisap-challenges/challenge2025",
        "dblp_url": "https://dblp.org/db/conf/sisap/sisap2025.html",
        "tira_url": "https://www.tira.io/tasks",
        "tasks": [
            {
                "number": 1,
                "slug": "task-1",
                "name": "Resource-limited indexing",
                "short_name": "Task 1",
            },
            {
                "number": 2,
                "slug": "task-2",
                "name": "K-nearest neighbor graph (metric self-join)",
                "short_name": "Task 2",
            },
        ],
        # Overview Table 1.  hforest and JLapeyra submitted without a paper.
        "papers": {
            "10.1007/978-3-032-06069-3_34": {"team": "cm-lll", "tasks": [1]},
            "10.1007/978-3-032-06069-3_35": {"team": "TeamDoubleFiltering", "tasks": [1]},
            "10.1007/978-3-032-06069-3_36": {"team": "DCC-UChile", "tasks": [2]},
            "10.1007/978-3-032-06069-3_37": {"team": "Crusty Coders", "tasks": [1, 2]},
            "10.1007/978-3-032-06069-3_38": {"team": "BrownCICESE", "tasks": [1, 2]},
        },
    },
    {
        "parent_venue": "SISAP",
        "year": 2026,
        "collection_id": "sisap2026",
        "official_url": "https://sisap-challenges.github.io/2026/",
        "tasks_url": "https://sisap-challenges.github.io/2026/",
        "evaluation_url": "https://sisap-challenges.github.io/2026/evaluation/",
        "leaderboard_url": "https://sisap-challenges.github.io/sisap26-leaderboard/",
        "accepted_url": "https://sisap.org/2026/accepted.html",
        # The Indexing Challenge section spans two pages of the Springer ToC.
        "proceedings_url": "https://link.springer.com/book/10.1007/978-3-032-42224-8?page=2",
        "proceedings_continuation_url": "https://link.springer.com/book/10.1007/978-3-032-42224-8?page=3",
        "conference_url": "https://sisap.org/2026/indexingchallenge.html",
        "github_repo_url": "https://github.com/sisap-challenges/challenge2026",
        "github_leaderboard_url": "https://github.com/sisap-challenges/sisap26-leaderboard",
        "github_files": {
            "teams": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/teams.json",
            "task1_wikipedia_test": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-1-wikipedia-20260614-test.csv",
            "task1_wikipedia_dev": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-1-wikipedia-dev.csv",
            "task1_wikipedia_small": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-1-wikipedia-small.csv",
            "task2_llama_dev": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-2-llama-dev.csv",
            "task2_llama_pg174": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-2-llama-pg174.csv",
            "task2_llama_test": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-2-llama.csv",
            "task3_fiqa": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-3-fiqa.csv",
            "task3_nq_test": "https://raw.githubusercontent.com/sisap-challenges/sisap26-leaderboard/main/data/task-3-nq-20260610-test.csv",
        },
        "dblp_url": "https://dblp.org/db/conf/sisap/sisap2026.html",
        "tira_url": "https://www.tira.io/task-overview/sisap-2026",
        "tasks": [
            {
                "number": 1,
                "slug": "task-1",
                "name": "K-nearest-neighbor graph (metric self-join)",
                "short_name": "Task 1",
            },
            {
                "number": 2,
                "slug": "task-2",
                "name": "Maximum Inner Product Search on LLM attention workloads",
                "short_name": "Task 2",
            },
            {
                "number": 3,
                "slug": "task-3",
                "name": "Indexing very sparse high-dimensional vectors",
                "short_name": "Task 3",
            },
        ],
        # Overview Table 2 (13 teams with papers).  Six further teams, including
        # wh-team, submitted runs without a paper in the proceedings.
        "papers": {
            "10.1007/978-3-032-42224-8_30": {"team": "seed-42", "tasks": [3]},
            "10.1007/978-3-032-42224-8_31": {"team": "baremetal-vectors", "tasks": [1]},
            "10.1007/978-3-032-42224-8_32": {"team": "Crusty Coders", "tasks": [1, 2, 3]},
            "10.1007/978-3-032-42224-8_33": {"team": "ketchup-needs-nuggets", "tasks": [1]},
            "10.1007/978-3-032-42224-8_34": {"team": "deglib", "tasks": [1, 2]},
            "10.1007/978-3-032-42224-8_35": {"team": "plain-local-search", "tasks": [1]},
            "10.1007/978-3-032-42224-8_36": {"team": "tusKANNy", "tasks": [3]},
            "10.1007/978-3-032-42224-8_37": {"team": "dream-team", "tasks": [1, 2]},
            "10.1007/978-3-032-42224-8_38": {"team": "pipnn", "tasks": [1]},
            "10.1007/978-3-032-42224-8_39": {"team": "basque-invaders", "tasks": [3]},
            "10.1007/978-3-032-42224-8_40": {"team": "luis", "tasks": [1, 2, 3]},
            "10.1007/978-3-032-42224-8_41": {"team": "hanswurst", "tasks": [1, 2, 3]},
            "10.1007/978-3-032-42224-8_42": {"team": "lzen402", "tasks": [1]},
        },
    },
]


def selected_editions(year: int | None = None) -> list[dict]:
    """Return all configured SISAP editions or one selected year."""
    if year is None:
        return list(SISAP_EDITIONS)
    return [edition for edition in SISAP_EDITIONS if edition["year"] == year]
