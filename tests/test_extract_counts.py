from src.extract_counts import (
    abstract_and_intro_window,
    extract_count,
    extract_run_count,
    is_plausible_count,
    RUN_PATTERNS,
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


def test_per_team_submission_cap_is_not_read_as_the_total():
    # Real bug found on eRisk 2018: "Each team could submit up to 5 runs or variants.
    # We received 45 contributions from 11 different institutions." — "45 contributions"
    # doesn't use the word "runs" at all, so the generic fallback matched the per-team
    # cap (5) instead, silently reporting a wrong number rather than null.
    window = "Each team could submit up to 5 runs or variants. We received 45 contributions from 11 different institutions."
    assert extract_count(window, RUN_PATTERNS) is None


ERISK_2025_INTRO = """
This year, the eRisk lab had 128 different teams registered. We finally received results
coming from 25 distinct teams: 67 runs for Task 1, 50 runs for Task 2, and 11 runs for
the pilot task.

2. Task 1: Search for Symptoms of Depression

We received 67 runs from 17 participating teams (see Table 2).

3. Task 2: Contextualized Early Detection
"""


def test_window_boundary_does_not_assume_a_numbered_intro_heading():
    # Real bug found on eRisk 2025: the paper has no numbered "1." heading at all, so its
    # first numbered heading is already "2. Task 1". Taking the *second* heading overall
    # (the old logic) meant "3. Task 2", which let the whole wrong Task-1-only subsection
    # ("17 participating teams") leak into the window. Must look for heading number >= 2
    # specifically, not just "the second heading found".
    window = abstract_and_intro_window(ERISK_2025_INTRO)
    assert "17 participating teams" not in window
    assert "25 distinct teams" in window


def test_sums_per_task_run_breakdown_including_non_numbered_task_name():
    # Same real eRisk 2025 case: "11 runs for the pilot task" has no task number, so the
    # original per-task pattern (requiring "Task \d+") missed it, silently summing to 117
    # instead of the true 128 (67 + 50 + 11).
    window = abstract_and_intro_window(ERISK_2025_INTRO)
    assert extract_run_count(window) == 128


def test_participation_phrasings_beyond_the_plain_received_from_form():
    # eRisk 2025 reports actual participation as "received results coming from 25
    # distinct teams"; the earlier pattern required the exact "results from N teams".
    w = "This year the lab had 128 different teams registered. We finally received results coming from 25 distinct teams."
    assert extract_count(w, TEAM_PATTERNS) == 25


def test_registration_only_counts_are_still_refused():
    # Registrations are not participation and would inflate coverage_ratio, so a paper
    # that only ever reports registrations must yield null rather than the bigger number.
    for w in [
        "We had 76 teams registered for the lab.",
        "The lab had 93 teams registered.",
        "16 groups registered to participate at PIR-CLEF 2018.",
    ]:
        assert extract_count(w, TEAM_PATTERNS) is None, w
