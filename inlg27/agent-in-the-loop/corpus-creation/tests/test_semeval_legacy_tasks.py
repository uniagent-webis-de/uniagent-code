from src.semeval_legacy_tasks import flag_order_conflicts, task_numbers


def test_task_number_named_either_way_round():
    assert task_numbers("our system for SemEval-2015 Task 10 and more", 2015) == [10]
    assert task_numbers("participated in Task 1 of SemEval 2015 evaluation", 2015) == [1]
    assert task_numbers("Task1 of S EM E VAL-2015", 2015) == [1]


def test_other_year_mentions_are_ignored():
    assert task_numbers("as in SemEval-2014 Task 9; we joined SemEval-2015 Task 10", 2015) == [10]


def test_several_tasks_are_all_returned():
    assert task_numbers("SemEval 2015 Task 1 and SemEval 2015 Task 2", 2015) == [1, 2]


def test_order_conflict_withholds_paper_between_two_agreeing_neighbours():
    ev = {f"S15-20{i:02d}": {"year": 2015, "status": "assigned", "task_numbers": [n]} for i, n in enumerate([3, 3, 7, 3, 3])}
    flag_order_conflicts(ev)
    assert [v["status"] for v in ev.values()] == ["assigned", "assigned", "order_conflict", "assigned", "assigned"]
