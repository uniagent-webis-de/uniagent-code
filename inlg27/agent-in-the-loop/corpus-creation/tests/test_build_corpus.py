import logging

from src.build_corpus import validate

LOGGER = logging.getLogger("test")


def make_task(task_id, overview_pdf_url, participant_pdf_urls, coverage_ratio=1.0):
    return {
        "task_id": task_id,
        "overview": {"pdf_url": overview_pdf_url, "title": "Overview", "authors": [], "is_umbrella": False},
        "participants": [
            {"title": "P", "authors": [], "pdf_url": url, "team_name": None, "code_urls": [], "tira_refs": []}
            for url in participant_pdf_urls
        ],
        "counts": {"notebook_papers": len(participant_pdf_urls), "teams_claimed_in_overview": None, "runs_claimed_in_overview": None, "coverage_ratio": coverage_ratio},
        "provenance": {"task_assignment_method": "section_grouping", "confidence": "high", "extracted_at": "2026-08-16"},
    }


def test_valid_corpus_passes():
    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf", "p2.pdf"]),
        make_task("t2", "ov2.pdf", ["p3.pdf"]),
    ]
    assert validate(tasks, LOGGER) is True


def test_duplicate_task_id_fails(caplog):
    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t1", "ov2.pdf", ["p2.pdf"]),
    ]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("duplicate task_id" in m for m in caplog.messages)


def test_duplicate_pdf_url_across_tasks_fails(caplog):
    tasks = [
        make_task("t1", "ov1.pdf", ["shared.pdf"]),
        make_task("t2", "ov2.pdf", ["shared.pdf"]),
    ]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("duplicate pdf_url" in m for m in caplog.messages)


def test_zero_participants_fails(caplog):
    tasks = [make_task("t1", "ov1.pdf", [])]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("0 participants" in m for m in caplog.messages)


def test_coverage_ratio_out_of_bounds_fails(caplog):
    tasks = [make_task("t1", "ov1.pdf", ["p1.pdf"], coverage_ratio=3.5)]
    with caplog.at_level(logging.ERROR):
        result = validate(tasks, LOGGER)
    assert result is False
    assert any("outside [0, 1.5]" in m for m in caplog.messages)


def test_null_coverage_ratio_is_allowed():
    tasks = [make_task("t1", "ov1.pdf", ["p1.pdf"], coverage_ratio=None)]
    assert validate(tasks, LOGGER) is True


def test_final_task_directories_match_the_assembled_tasks(tmp_path, monkeypatch):
    from src import build_corpus

    final_dir = tmp_path / "final"
    (final_dir / "t1").mkdir(parents=True)
    (final_dir / "stale-task").mkdir()
    monkeypatch.setattr(build_corpus, "FINAL_DIR", final_dir)

    assert build_corpus.validate_final_task_directories(
        [make_task("t1", "ov1.pdf", ["p1.pdf"])], LOGGER
    ) is False


def test_final_task_directory_validation_rejects_missing_directory(tmp_path, monkeypatch):
    from src import build_corpus

    final_dir = tmp_path / "final"
    final_dir.mkdir()
    monkeypatch.setattr(build_corpus, "FINAL_DIR", final_dir)

    assert build_corpus.validate_final_task_directories(
        [make_task("t1", "ov1.pdf", ["p1.pdf"])], LOGGER
    ) is False


def test_select_corpus_emits_all_candidates_without_a_target_cap():
    from src.build_corpus import select_corpus

    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t2", "ov2.pdf", ["p2.pdf"]),
    ]
    selected = select_corpus(tasks, None, LOGGER)
    assert {task["task_id"] for task in selected} == {"t1", "t2"}


def test_select_corpus_keeps_optional_target_cap():
    from src.build_corpus import select_corpus

    tasks = [
        make_task("t1", "ov1.pdf", ["p1.pdf"]),
        make_task("t2", "ov2.pdf", ["p2.pdf"]),
    ]
    assert len(select_corpus(tasks, 1, LOGGER)) == 1


def test_fulltext_paths_are_published_on_the_records():
    # Consumers must be able to go from a corpus entry straight to its parsed text,
    # rather than deriving filenames from pdf_url by string manipulation.
    from src.build_corpus import join_fulltext_paths

    task = make_task("t1", "https://x/ov.pdf", ["https://x/p1.pdf", "https://x/p2.pdf"])
    manifest = {
        "https://x/ov.pdf": {
            "pdf_path": "data/final/t1/overview/overview.pdf",
            "markdown_path": "data/final/t1/overview/overview.txt.md",
            "n_figures": 0,
            "n_tables": 3,
        },
        "https://x/p1.pdf": {
            "pdf_path": "data/final/t1/papers/p1/paper.pdf",
            "markdown_path": "data/final/t1/papers/p1/paper.txt.md",
            "n_figures": 2,
            "n_tables": 1,
        },
    }
    join_fulltext_paths(task, manifest, LOGGER)

    assert task["overview"]["pdf_path"] == "data/final/t1/overview/overview.pdf"
    assert task["overview"]["fulltext_path"] == "data/final/t1/overview/overview.txt.md"
    assert task["participants"][0]["pdf_path"] == "data/final/t1/papers/p1/paper.pdf"
    assert task["participants"][0]["fulltext_path"] == "data/final/t1/papers/p1/paper.txt.md"
    # An unparsed document yields null rather than a fabricated path.
    assert task["participants"][1]["fulltext_path"] is None
    # Figure/table counts ride along so they are queryable from the corpus files.
    assert task["overview"]["n_tables"] == 3
    assert task["participants"][0]["n_figures"] == 2
    assert task["participants"][1]["n_figures"] == 0


def test_fulltext_join_is_a_no_op_when_stage_7_has_not_run():
    from src.build_corpus import join_fulltext_paths

    task = make_task("t1", "https://x/ov.pdf", ["https://x/p1.pdf"])
    join_fulltext_paths(task, {}, LOGGER)
    assert "fulltext_path" not in task["overview"]


def test_subtask_indexes_list_multi_subtask_papers_in_each_subtask(tmp_path, monkeypatch):
    import json
    import src.corpus_paths as corpus_paths
    from src.build_corpus import write_subtask_indexes

    monkeypatch.setattr(corpus_paths, "FINAL_DIR", tmp_path)
    task = make_task("sisap2026-indexing-challenge", "ov.pdf", ["https://x.org/a_1.pdf", "https://x.org/b_2.pdf"])
    task["participants"][0]["task_numbers"] = [1, 2]
    task["participants"][1]["task_numbers"] = [2]
    task["source"] = {"subtasks": [{"number": 1, "name": "One"}, {"number": 2, "name": "Two"}]}
    write_subtask_indexes(task)

    subtasks = tmp_path / "sisap2026-indexing-challenge" / "subtasks"
    one = json.loads((subtasks / "task-1.json").read_text())
    two = json.loads((subtasks / "task-2.json").read_text())
    assert [paper["paper_dir"] for paper in one["papers"]] == ["papers/a_1"]
    assert [paper["paper_dir"] for paper in two["papers"]] == ["papers/a_1", "papers/b_2"]

    plain = make_task("clef2024-lab", "ov.pdf", ["https://x.org/c.pdf"])
    plain["source"] = {}
    write_subtask_indexes(plain)
    assert not (tmp_path / "clef2024-lab" / "subtasks").exists()


def test_drop_non_papers():
    import logging

    from src.build_corpus import drop_non_papers

    def rec(url, pages, chars):
        return {"pdf_url": url, "pages": pages, "chars": chars}

    def task(tid, ov, parts):
        return {"task_id": tid, "overview": {"pdf_url": ov, "title": "T"}, "participants": [{"pdf_url": u, "title": "T"} for u in parts]}

    manifest = {
        "o1": rec("o1", 8, 40000), "a": rec("a", 2, 9000), "b": rec("b", 6, 30000),
        "abs": rec("abs", 1, 1500), "x/poster.pdf": rec("x/poster.pdf", 4, 20000),
        "o2": rec("o2", 1, 2900), "c": rec("c", 5, 20000), "d": rec("d", 5, 20000),
        "o3": rec("o3", 8, 40000), "e": rec("e", 5, 20000), "thin": rec("thin", 3, 2800),
    }
    tasks = [
        task("keep", "o1", ["a", "b", "abs", "x/poster.pdf"]),  # 2 real papers remain
        task("bad-overview", "o2", ["c", "d"]),
        task("too-few", "o3", ["e", "thin"]),
    ]
    kept, dropped = drop_non_papers(tasks, manifest, logging.getLogger("t"))
    assert [t["task_id"] for t in kept] == ["keep"]
    assert [p["pdf_url"] for p in kept[0]["participants"]] == ["a", "b"]
    assert {d[0] for d in dropped} == {"keep", "bad-overview", "too-few"}


def test_write_summary_csv(tmp_path):
    import csv

    from src.build_corpus import write_summary_csv

    t = {"task_id": "x2020-a", "task_name": "A", "parent_venue": "X", "year": 2020, "field": "IR",
         "participants": [{}, {}], "source": {"proceedings_url": "http://p", "track_url": "http://t"}}
    write_summary_csv([t], tmp_path / "s.csv")
    row = next(csv.DictReader((tmp_path / "s.csv").open()))
    assert (row["field"], row["notebook_papers"], row["source_url"], row["task_page_url"]) == ("IR", "2", "http://p", "http://t")


def test_drop_non_papers_catches_topic_files_and_invited_talks():
    import logging

    from src.build_corpus import drop_non_papers

    def rec(url):
        return {"pdf_url": url, "pages": 5, "chars": 20000}

    urls = ["a/NTCIR3-WEB-X.pdf", "a/NTCIR3-INV-HarmanD.pdf", "a/NTCIR3-TOPIC-WEB.pdf", "a/inv-pap8-CR.pdf", "b"]
    manifest = {u: rec(u) for u in urls + ["ov"]}
    task = {"task_id": "t", "overview": {"pdf_url": "ov", "title": "O"},
            "participants": [{"pdf_url": u, "title": "Full list Japanese" if u == "b" else "P"} for u in urls]}
    kept, _ = drop_non_papers([task], manifest, logging.getLogger("t"))
    assert [p["pdf_url"] for p in kept[0]["participants"]] == ["a/NTCIR3-WEB-X.pdf", "a/inv-pap8-CR.pdf"]


def test_prune_unreferenced_removes_orphans_and_stale_manifest_rows(tmp_path, monkeypatch):
    import json
    import logging

    from src import build_corpus as bc

    monkeypatch.setattr(bc, "FINAL_DIR", tmp_path)
    monkeypatch.setattr(bc, "MANIFEST_PATH", tmp_path / "manifest.jsonl")
    monkeypatch.setattr(bc, "task_dir", lambda tid: tmp_path / tid)
    monkeypatch.setattr(bc, "participant_dir", lambda tid, url: tmp_path / tid / "papers" / url)
    (tmp_path / "t" / "papers" / "keep").mkdir(parents=True)
    (tmp_path / "t" / "papers" / "orphan").mkdir(parents=True)
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"task_id": "t", "pdf_url": "keep"}) + "\n" + json.dumps({"task_id": "gone", "pdf_url": "x"}) + "\n"
    )
    task = {"task_id": "t", "overview": {"pdf_url": "ov"}, "participants": [{"pdf_url": "keep"}]}
    bc.prune_unreferenced([task], logging.getLogger("t"))
    assert (tmp_path / "t" / "papers" / "keep").exists() and not (tmp_path / "t" / "papers" / "orphan").exists()
    assert [json.loads(l)["task_id"] for l in (tmp_path / "manifest.jsonl").read_text().splitlines()] == ["t"]


def test_task_whose_filed_overview_is_a_participant_paper_is_dropped():
    import logging

    from src.build_corpus import PARTICIPANT_PAPERS_FILED_AS_OVERVIEW, drop_non_papers

    ov = sorted(PARTICIPANT_PAPERS_FILED_AS_OVERVIEW)[0]
    good = {"pdf_url": "p1", "title": "T"}
    manifest = {u: {"pdf_url": u, "pages": 8, "chars": 40000} for u in (ov, "p1", "p2")}
    task = {"task_id": "t", "overview": {"pdf_url": ov, "title": "Report"}, "participants": [good, {"pdf_url": "p2", "title": "T"}]}
    kept, dropped = drop_non_papers([task], manifest, logging.getLogger("t"))
    assert kept == [] and {d[2] for d in dropped} == {ov, "p1", "p2"}


def test_extracted_authors_fill_only_missing_ones():
    from src.build_corpus import join_extracted_authors

    task = {"task_id": "t", "overview": {"pdf_url": "o", "authors": ["Real Author"]},
            "participants": [{"pdf_url": "a", "authors": []}, {"pdf_url": "b", "authors": []}]}
    join_extracted_authors(task, {"t|a": ["Found Name"], "t|o": ["Ignored"]})
    assert task["overview"]["authors"] == ["Real Author"] and task["overview"]["authors_source"] == "source_metadata"
    assert task["participants"][0]["authors"] == ["Found Name"]
    assert task["participants"][0]["authors_source"] == "extracted_from_text"
    assert task["participants"][1]["authors"] == [] and task["participants"][1]["authors_source"] is None
