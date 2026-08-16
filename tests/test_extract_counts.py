from src.extract_counts import (
    abstract_and_intro_window,
    extract_count,
    extract_run_count,
    is_plausible_count,
    TEAM_PATTERNS,
)

ERISK_2023_INTRO = """
1. Introduction

In 2023, eRisk featured three campaign-style tasks.
A total of 98 teams registered for the lab, out of which we received results from 20 teams, with
37 runs for Task 1, 48 runs for Task 2, and 20 runs for Task 3.

2. Task 1: Search for Symptoms of Depression

Task 1 introduced a novel challenge. We received 37 runs from 10 participating teams (see Table 2).
"""


def test_window_stops_before_first_task_subsection():
    window = abstract_and_intro_window(ERISK_2023_INTRO)
    assert "10 participating teams" not in window
    assert "received results from 20 teams" in window


def test_prefers_actual_participation_over_registration_count():
    window = abstract_and_intro_window(ERISK_2023_INTRO)
    assert extract_count(window, TEAM_PATTERNS) == 20


def test_sums_per_task_run_breakdown_when_no_explicit_total():
    window = abstract_and_intro_window(ERISK_2023_INTRO)
    assert extract_run_count(window) == 105


def test_teams_up_idiom_does_not_match_as_a_count():
    # Real bug found on CENTRE@CLEF 2019: "CENTRE@CLEF 2019 teams up with the
    # Open-Source IR Replicability Challenge" is a verb, not a participant count.
    text = "For Task 1 and Task 2, CENTRE@CLEF 2019 teams up with the Open-Source IR Replicability Challenge."
    assert extract_count(text, TEAM_PATTERNS) is None


def test_implausible_year_shaped_count_is_rejected():
    assert is_plausible_count(2019) is False
    assert is_plausible_count(0) is False
    assert is_plausible_count(20) is True


def test_elliptical_two_task_sentence_is_not_silently_misread():
    # "14 and 4 teams participated in Task 1 and Task 2, respectively" — the regex
    # can only find "4 teams participated" (the second, elliptically-written figure),
    # not the intended 14. This is exactly what the notebook-papers-vs-teams ratio
    # check in process_task() is for; extract_count() itself has no way to know this
    # number is wrong, so it still returns 4 here.
    window = "Ultimately, 14 and 4 teams participated in Task 1 and Task 2, respectively."
    assert extract_count(window, TEAM_PATTERNS) == 4
