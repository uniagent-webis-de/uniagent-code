from argparse import Namespace

from src.run_pipeline import run_pipeline, stage_commands


def make_args(**overrides):
    values = {
        "volume": None,
        "confidence": "high",
        "task_id": None,
        "download_workers": 8,
        "semeval_year": None,
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
