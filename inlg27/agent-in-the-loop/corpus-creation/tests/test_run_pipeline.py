from argparse import Namespace

from src.run_pipeline import run_pipeline, stage_commands


def make_args(**overrides):
    values = {
        "volume": None,
        "confidence": "high",
        "task_id": None,
        "download_workers": 8,
        "semeval_year": None,
        "trec_year": None,
        "ntcir_edition": None,
        "fire_year": None,
        "mediaeval_year": None,
        "target": None,
        "ocr_server_url": None,
        "ocr_language": "eng",
        "only_needs_ocr": False,
        "pdffigures2_dir": None,
        "pdffigures2_jar": None,
        "pdffigures2_dpi": 150,
        "pdffigures2_image_format": "png",
        "pdffigures2_threads": 4,
    }
    values.update(overrides)
    return Namespace(**values)


def test_stage_order_matches_the_canonical_pipeline():
    names = [name for name, _ in stage_commands(make_args())]
    assert names == [
        "fetch_volumes",
        "parse_sections",
        "group_tasks",
        "fetch_semeval",
        "collect_semeval",
        "fetch_trec",
        "collect_trec",
        "fetch_ntcir",
        "collect_ntcir",
        "fetch_fire",
        "collect_fire",
        "fetch_mediaeval",
        "collect_mediaeval",
        "merge_candidates",
        "download_papers",
        "parse_fulltext",
        "extract_figs_tbls",
        "extract_counts",
        "find_code",
        "build_corpus",
    ]


def test_pipeline_stops_after_a_failed_stage(monkeypatch):
    calls = []

    class FakeProcess:
        def __init__(self, returncode):
            self.stdout = iter(["stage output\n"])
            self.returncode = returncode

        def wait(self):
            return self.returncode

    def fake_popen(command, cwd, stdout, stderr, text, bufsize):
        calls.append(command[1].split("/")[-1])
        return FakeProcess(1 if len(calls) == 2 else 0)

    monkeypatch.setattr("src.run_pipeline.subprocess.Popen", fake_popen)
    assert run_pipeline(make_args()) == 1
    assert len(calls) == 2


def test_trec_year_is_forwarded_to_both_trec_stages():
    commands = dict(stage_commands(make_args(trec_year=2025)))
    assert commands["fetch_trec"] == ["fetch_trec.py", "--year", "2025"]
    assert commands["collect_trec"] == ["collect_trec.py", "--year", "2025"]


def test_ntcir_edition_is_forwarded_to_both_ntcir_stages():
    commands = dict(stage_commands(make_args(ntcir_edition=18)))
    assert commands["fetch_ntcir"] == ["fetch_ntcir.py", "--edition", "18"]
    assert commands["collect_ntcir"] == ["collect_ntcir.py", "--edition", "18"]


def test_fire_year_is_forwarded_to_both_fire_stages():
    commands = dict(stage_commands(make_args(fire_year=2025)))
    assert commands["fetch_fire"] == ["fetch_fire.py", "--year", "2025"]
    assert commands["collect_fire"] == ["collect_fire.py", "--year", "2025"]


def test_mediaeval_year_is_forwarded_to_both_mediaeval_stages():
    commands = dict(stage_commands(make_args(mediaeval_year=2022)))
    assert commands["fetch_mediaeval"] == ["fetch_mediaeval.py", "--year", "2022"]
    assert commands["collect_mediaeval"] == ["collect_mediaeval.py", "--year", "2022"]
