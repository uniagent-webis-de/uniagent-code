#!/usr/bin/env python3

import json
import os
import subprocess
import tempfile
from pathlib import Path

import click

NANO_AIU_PER_AI_CREDIT = 1_000_000_000

LOGIN_TOKEN_ENV_VAR = "GH_TOKEN"

PROMPT_TEMPLATE = """\
You are given the full Markdown text of an academic paper below. Write a \
single concise paragraph (3-6 sentences) that summarizes the papers main \
contribution suitable for a related-work section. Output \
only the summary paragraph itself, with no preamble, headings, or markdown \
formatting.

---
{paper}
---
"""


def require_login_token(env: dict) -> str:
    token = env.get(LOGIN_TOKEN_ENV_VAR)
    if not token:
        raise click.ClickException(
            f"Environment variable {LOGIN_TOKEN_ENV_VAR} must be set to a "
            "GitHub token with Copilot access so the baseline can authenticate "
            "(see `copilot help environment`)."
        )
    return token


def run_copilot(command: list[str], env: dict) -> subprocess.CompletedProcess:
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        message = f"Command {command} failed with exit code {result.returncode}"
        if details:
            message += f":\n{details}"
        raise RuntimeError(message)
    return result


def read_ai_credits(usage_file: Path) -> float | None:
    try:
        usage = json.loads(usage_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    nano_aiu = usage.get("totalNanoAiu")
    if nano_aiu is None:
        return None
    return nano_aiu / NANO_AIU_PER_AI_CREDIT


def summarize_paper(
    markdown: str, env: dict, model: str | None
) -> tuple[str, float | None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        usage_file = Path(tmp_dir) / "usage.json"
        command = [
            "copilot",
            "--prompt",
            PROMPT_TEMPLATE.format(paper=markdown),
            "--silent",
            "--allow-all-tools",
            "--no-color",
            "--usage-output-file",
            str(usage_file),
        ]
        if model:
            command += ["--model", model]

        result = run_copilot(command, env)
        ai_credits = read_ai_credits(usage_file)

    summary = result.stdout.strip()
    if not summary:
        raise ValueError("Copilot returned an empty summary")
    return summary, ai_credits


def find_papers(input_directory: Path) -> list[Path]:
    papers = sorted(input_directory.rglob("paper.txt.md"))
    if not papers:
        raise ValueError(f"No paper.txt.md files found in {input_directory}")

    ids = [paper.parent.name for paper in papers]
    if len(ids) != len(set(ids)):
        raise ValueError("Paper directory names must be unique")
    return papers


def generate_summaries(
    input_directory: Path,
    output_file: Path,
    model: str | None,
    env: dict,
) -> None:
    require_login_token(env)

    papers = find_papers(input_directory)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as output:
        for paper in papers:
            markdown = paper.read_text(encoding="utf-8")
            summary, ai_credits = summarize_paper(markdown, env, model)

            credits_display = (
                f"{ai_credits:.4f}" if ai_credits is not None else "unknown"
            )
            click.echo(
                f"[{paper.parent.name}] AI credits used: {credits_display}",
                err=True,
            )

            record = {"id": paper.parent.name, "summary": summary}
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


@click.command()
@click.option(
    "--input",
    "input_directory",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory containing paper directories with paper.txt.md files.",
)
@click.option(
    "--output",
    "output_file",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Destination JSONL file.",
)
@click.option(
    "--model",
    "model",
    default=None,
    help="Copilot model to use (defaults to Copilot's own choice).",
)
def main(
    input_directory: Path,
    output_file: Path,
    model: str | None,
) -> None:
    try:
        generate_summaries(input_directory, output_file, model, os.environ.copy())
    except (ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    main()
