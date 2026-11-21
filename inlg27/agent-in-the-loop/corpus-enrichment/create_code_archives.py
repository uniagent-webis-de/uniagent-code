#!/usr/bin/env python3
"""Add code archives to one subtask directory produced by
PROTOCOL_TO_SPLIT_SHARED_TASKS_INTO_SUBTASKS.md.

Reads `code-repositories.json` of the shared-task directory X (paper_id -> list
of {url, commit, branch, tasks}), keeps only the papers present in
`Y/task_<n>/papers/` and the repositories used for subtask `task<n>`, and writes
`Y/task_<n>/code/<paper_id>/<repo-name>.zip`.

Each repository is cloned, checked out at the expected commit (verified via
`git rev-parse HEAD`; a warning is printed if the commit is no longer on the
recorded branch), stripped of all `.git` entries, and zipped (top-level folder
= repo name).

Usage (needs git; run in Docker, e.g. `docker run --rm -v $PWD:/w -w /w python:3.12 ...`):
  python create_code_archives.py --repositories X/code-repositories.json --subtask-dir Y/task_1
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def verify(repo_dir, commit, branch):
    head = git("rev-parse", "HEAD", cwd=repo_dir)
    if head != commit:
        raise RuntimeError(f"HEAD is {head}, expected {commit}")
    if git("status", "--porcelain", cwd=repo_dir):
        raise RuntimeError("working tree is not clean after checkout")
    if branch:
        branches = [branch] if isinstance(branch, str) else branch
        containing = git("branch", "-r", "--contains", commit, cwd=repo_dir).split()
        if not any(f"origin/{b}" in containing for b in branches):
            # Branches move after submission, so this is only a warning.
            print(
                f"WARN commit {commit[:8]} is not on origin/{branches} anymore",
                file=sys.stderr,
            )


def zip_dir(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            zf.write(path, Path(src.name) / path.relative_to(src))


def process(paper, entry, out_dir, force):
    url, commit, branch = entry["url"], entry["commit"], entry.get("branch")
    name = url.rstrip("/").split("/")[-1]
    dest = out_dir / paper / f"{name}.zip"
    if dest.exists() and not force:
        print(f"skip {dest} (exists)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / name
        git("clone", "--quiet", url, str(repo_dir))
        git("checkout", "--quiet", "--detach", commit, cwd=repo_dir)
        if (repo_dir / ".gitmodules").exists():
            git("submodule", "update", "--init", "--recursive", cwd=repo_dir)
        verify(repo_dir, commit, branch)
        for git_entry in list(repo_dir.rglob(".git")):
            if git_entry.is_dir():
                shutil.rmtree(git_entry)
            else:
                git_entry.unlink()
        zip_dir(repo_dir, dest)
    print(f"ok   {dest} ({url} @ {commit[:8]})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repositories", type=Path, required=True, help="X/code-repositories.json")
    parser.add_argument("--subtask-dir", type=Path, required=True, help="Y/task_<n>")
    parser.add_argument("--force", action="store_true", help="overwrite existing zips")
    args = parser.parse_args()

    match = re.fullmatch(r"task_(\d+)", args.subtask_dir.resolve().name)
    if not match:
        sys.exit(f"{args.subtask_dir} is not named task_<n>")
    task = f"task{match.group(1)}"
    papers = {p.name for p in (args.subtask_dir / "papers").iterdir() if p.is_dir()}
    out_dir = args.subtask_dir / "code"

    failures = 0
    for paper, repos in json.loads(args.repositories.read_text()).items():
        if paper not in papers:
            continue
        for entry in repos:
            if task not in entry.get("tasks", []):
                continue
            try:
                process(paper, entry, out_dir, args.force)
            except Exception as e:
                failures += 1
                detail = getattr(e, "stderr", "") or ""
                print(f"FAIL {paper} {entry['url']}: {e} {detail}", file=sys.stderr)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
