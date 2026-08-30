import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseline import (
    LOGIN_TOKEN_ENV_VAR,
    find_papers,
    generate_summaries,
    main,
    read_ai_credits,
    require_login_token,
    summarize_paper,
)


def write_usage_file(command, nano_aiu=2_500_000_000):
    usage_file = Path(command[command.index("--usage-output-file") + 1])
    usage_file.write_text(json.dumps({"totalNanoAiu": nano_aiu}), encoding="utf-8")


def test_require_login_token_missing():
    with pytest.raises(Exception, match=LOGIN_TOKEN_ENV_VAR):
        require_login_token({})


def test_require_login_token_present():
    assert require_login_token({LOGIN_TOKEN_ENV_VAR: "secret"}) == "secret"


def test_summarize_paper_returns_stdout_and_credits(monkeypatch):
    def fake_run(command, **kwargs):
        assert "--allow-all-tools" in command
        assert "some paper text" in command[command.index("--prompt") + 1]
        write_usage_file(command, nano_aiu=1_500_000_000)
        return subprocess.CompletedProcess(
            command, 0, stdout="A great summary.\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    summary, ai_credits = summarize_paper("some paper text", {}, None)

    assert summary == "A great summary."
    assert ai_credits == pytest.approx(1.5)


def test_summarize_paper_passes_model(monkeypatch):
    def fake_run(command, **kwargs):
        assert command[-2:] == ["--model", "gpt-5"]
        write_usage_file(command)
        return subprocess.CompletedProcess(command, 0, stdout="Summary", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    summarize_paper("text", {}, "gpt-5")


def test_summarize_paper_raises_on_empty_output(monkeypatch):
    def fake_run(command, **kwargs):
        write_usage_file(command)
        return subprocess.CompletedProcess(command, 0, stdout="  \n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="empty summary"):
        summarize_paper("text", {}, None)


def test_summarize_paper_surfaces_stderr_on_failure(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="Error: authentication failed\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="authentication failed"):
        summarize_paper("text", {}, None)


def test_read_ai_credits_missing_file_returns_none(tmp_path):
    assert read_ai_credits(tmp_path / "missing.json") is None


def test_read_ai_credits_parses_nano_aiu(tmp_path):
    usage_file = tmp_path / "usage.json"
    usage_file.write_text(json.dumps({"totalNanoAiu": 500_000_000}), encoding="utf-8")

    assert read_ai_credits(usage_file) == pytest.approx(0.5)


def test_find_papers_requires_paper_files(tmp_path):
    with pytest.raises(ValueError, match="No paper.txt.md"):
        find_papers(tmp_path)


def test_generate_summaries_end_to_end(tmp_path, monkeypatch, capsys):
    input_directory = tmp_path / "papers"
    paper_directory = input_directory / "172"
    paper_directory.mkdir(parents=True)
    (paper_directory / "paper.txt.md").write_text(
        "# Paper Title\n\nSome content.\n", encoding="utf-8"
    )
    output_file = tmp_path / "output" / "predictions.jsonl"

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        write_usage_file(command, nano_aiu=2_000_000_000)
        return subprocess.CompletedProcess(
            command, 0, stdout="Generated summary.\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    generate_summaries(
        input_directory, output_file, None, {LOGIN_TOKEN_ENV_VAR: "secret"}
    )

    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "id": "172",
        "summary": "Generated summary.",
    }
    assert "--prompt" in calls[0]
    assert "[172] AI credits used: 2.0000" in capsys.readouterr().err


def test_generate_summaries_requires_token(tmp_path):
    with pytest.raises(Exception, match=LOGIN_TOKEN_ENV_VAR):
        generate_summaries(tmp_path, tmp_path / "out.jsonl", None, {})


def test_cli_surfaces_copilot_failure_details(tmp_path, monkeypatch):
    input_directory = tmp_path / "papers"
    paper_directory = input_directory / "172"
    paper_directory.mkdir(parents=True)
    (paper_directory / "paper.txt.md").write_text(
        "# Paper Title\n\nSome content.\n", encoding="utf-8"
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="Error: authentication failed\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CliRunner().invoke(
        main,
        ["--input", str(input_directory), "--output", str(tmp_path / "out.jsonl")],
        env={LOGIN_TOKEN_ENV_VAR: "bad-token"},
    )

    assert result.exit_code != 0
    assert "authentication failed" in result.output


def test_cli_fails_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv(LOGIN_TOKEN_ENV_VAR, raising=False)
    input_directory = tmp_path / "papers"
    input_directory.mkdir()

    result = CliRunner().invoke(
        main,
        ["--input", str(input_directory), "--output", str(tmp_path / "out.jsonl")],
    )

    assert result.exit_code != 0
    assert LOGIN_TOKEN_ENV_VAR in result.output
