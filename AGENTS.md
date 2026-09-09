# AGENTS.md

Guidance for coding agents developing a shared-task submission (baseline or
participant system) in this repository.

## Repository layout

This repository hosts multiple, independent UniAgent shared tasks. Each has
its own subdirectory at the repo root:

- `cikm26/` — UniAgent 2026 (CIKM'26): business-trip application review and
  retrieval sub-tasks.
  - `cikm26/baselines/` — reference submissions.
  - `cikm26/datasets/` — task datasets (spot-check inputs, qrels, retrieval
    corpora).
  - `cikm26/dataset-construction/` — how datasets were built.
  - `cikm26/text-processing/` — shared text-processing utilities used to
    prepare corpora.
  - `cikm26/event-logging-contract/` — tool-call logging contract (see
    below).
- `clef27/` — placeholder task (`README.md` is currently `TBD`).
- `inlg27/agent-in-the-loop/` — shared-task-overview generation task, with
  its own `baselines/`, `corpora/`, `corpus-creation/`, and `evaluation/`
  subdirectories.
- `thesis-raspberry-pi/` — unrelated thesis artifacts, not a shared task.

Each task's baselines are self-contained: their own `requirements.txt`,
`Dockerfile`, `README.md`, and (for cikm26 baselines) a `test_baseline.py`.
There is no repo-wide build system; work inside the relevant baseline's
directory using its own tooling.

## Workflow for developing a submission

1. **Ask the participant which task/track they want to submit to** before
   writing any code. Do not assume — the tasks have different input
   formats, tools, and evaluation criteria. Current options:
   - `cikm26` business-trip review (accept/reject applications)
   - `cikm26` retrieval (German/English document retrieval)
   - `clef27` (not yet defined — check `clef27/README.md` for updates
     before proceeding)
   - `inlg27` agent-in-the-loop (shared-task-overview generation from
     papers/submissions)

2. **Read the existing baselines for that task first**, in
   `<task>/baselines/` (cikm26) or `<task>/baseline-*/` (inlg27). They show
   the expected input dataset layout, output format (typically
   `predictions.jsonl`), the `tira-cli code-submission` invocation, and the
   `Dockerfile`/`requirements.txt` conventions a new submission should
   follow. Prefer extending or copying the structure of the closest
   existing baseline over inventing a new layout. For cikm26, note the
   spectrum from deterministic baselines (`business-trip-always-rejected`)
   to tool-using agents (`business-trip-smolagents`,
   `business-trip-smolagents-with-retrieval`) to retrieval-only baselines
   (`retrieval-baseline-pyterrier`, `retrieval-baseline-pyserini`).

3. **If the submission exposes tools to a model** (any cikm26 agent
   baseline, and any similar tool-using baseline in other tasks), read
   `cikm26/event-logging-contract/README.md` and comply with it: log every
   tool call as one JSON-Lines object (`case_id`, `tool`, `arguments`,
   `status`, `error`, `timestamp`), including failures, with arguments
   bound by name and truncated per the contract's rules. Reuse or mirror
   `cikm26/baselines/business-trip-smolagents-with-retrieval/tool_logging.py`
   as the reference implementation for a new agent framework, and cite the
   contract from the new baseline's README.

4. **Write/adapt tests.** Baselines that have one use `test_baseline.py`
   run with `pytest` (some set `PYTHONPATH=.`; check the baseline's README
   for the exact command). Match this convention for new submissions in
   the same task.

5. **Verify locally before submission**: run the baseline's own example
   command from its README against the task's spot-check dataset under
   `<task>/datasets/` (or `corpora/` for inlg27), confirm the output format
   matches, then use the `tira-cli code-submission ... --dry-run` command
   shown in that baseline's README as the template for the real
   submission.

## Conventions observed across baselines

- Output is one JSON object per line (`predictions.jsonl` or equivalent),
  never pretty-printed multi-line JSON.
- Every baseline README documents: what it does, how to run it locally,
  any required environment variables/credentials, and the exact
  `tira-cli code-submission` command.
- Baselines fail fast and loudly (e.g. missing endpoint/credentials,
  malformed model output) rather than silently substituting a default
  result.
- Use short-lived, dedicated credentials (API keys, tokens) for any
  external service a baseline calls — never production credentials.
