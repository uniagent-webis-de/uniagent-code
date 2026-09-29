# AGENTS.md

Guidance for coding agents developing a shared-task submission (baseline or
participant system) in this repository.

## Repository layout

This repository hosts multiple, independent UniAgent shared tasks. Each has
its own subdirectory at the repo root:

- `cikm26/` — UniAgent 2026 (CIKM'26): retrieval (Task 1) and
  application-solving (Task 2: business trips, expense reimbursements,
  procurements) sub-tasks.
  - `cikm26/baselines/` — reference submissions.
  - `cikm26/datasets/` — task datasets (spot-check inputs, qrels, retrieval
    corpora).
  - `cikm26/dataset-construction/` — how datasets were built.
  - `cikm26/text-processing/` — shared text-processing utilities used to
    prepare corpora.
  - `cikm26/event-logging-contract/` — tool-call logging contract (see
    below).
  - `cikm26/evaluation/` — shared submission evaluator (`evaluate_submission.py`).
  - `cikm26/near-duplicate-detection/` — near-duplicate detection tooling for
    retrieval corpora.
- `clef27/` — placeholder task (`README.md` is currently `TBD`).
- `inlg27/agent-in-the-loop/` — shared-task-overview generation task, with
  its own `baselines/`, `corpora/`, `corpus-creation/`, and `evaluation/`
  subdirectories.

Each task's baselines are self-contained: their own `Dockerfile` and
`README.md`, plus a `requirements.txt` and `test_baseline.py` for baselines
with dependencies/logic worth testing (the purely deterministic cikm26
baselines `solving-always-rejected`/`solving-always-allow` have neither,
since there is nothing to install or unit-test beyond a fixed output).
There is no repo-wide build system; work inside the relevant baseline's
directory using its own tooling.

## Workflow for developing a submission

1. **Ask the participant which task/track they want to submit to. Also ask if Docker should be used (which is recommended, see step 5)** before
   writing any code. Do not assume — the tasks have different input
   formats, tools, and evaluation criteria. Current options:
   - `cikm26` retrieval (Task 1: German/English document retrieval)
   - `cikm26` solving (Task 2: accept/reject business-trip,
     expense-reimbursement, and procurement applications — the application
     type is determined by its directory name, e.g. `dienstreiseantrag...`,
     `auslagenerstattung...`, `beschaffungsantrag...`)
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
   spectrum from deterministic baselines (`solving-always-rejected`,
   `solving-always-allow`) to tool-using agents (`solving-smolagents`,
   `solving-smolagents-with-retrieval`) to retrieval-only baselines
   (`retrieval-baseline-pyterrier`, `retrieval-baseline-pyterrier-smolagent`,
   `retrieval-baseline-pyserini`).

3. **If the submission exposes tools to a model** (any cikm26 agent
   baseline, and any similar tool-using baseline in other tasks), read
   `cikm26/event-logging-contract/README.md` and comply with it: log every
   tool call as one JSON-Lines object (`case_id`, `tool`, `arguments`,
   `status`, `error`, `timestamp`), including failures, with arguments
   bound by name and truncated per the contract's rules. Reuse or mirror
   `cikm26/baselines/solving-smolagents-with-retrieval/event_logging.py`
   as the reference implementation for a new agent framework, and cite the
   contract from the new baseline's README.

4. **Write/adapt tests.** Baselines that have one use `test_baseline.py`
   run with `pytest` (some set `PYTHONPATH=.`; check the baseline's README
   for the exact command). Match this convention for new submissions in
   the same task.

5. **Run and test everything inside Docker, never in an ad-hoc venv.**
   Baselines pin heavy, sometimes native (e.g. JVM-based PyTerrier)
   dependencies in their `Dockerfile`/`requirements.txt`; do not `pip
   install` them into a local virtualenv to "just run the tests". Build and
   run the baseline's own `Dockerfile` as shown in its README (most
   baselines document a `docker build` + `docker run --entrypoint python -m
   unittest ...` invocation), or use an existing `.devcontainer/` where one
   is already provided (e.g. the retrieval baselines), instead of creating a
   new environment.

6. **Verify locally before submission**: run the baseline's own example
   command from its README against the task's spot-check dataset under
   `<task>/datasets/` (or `corpora/` for inlg27), confirm the output format
   matches, then use the `tira-cli code-submission ... --dry-run` command
   shown in that baseline's README as the template for the real
   submission. For cikm26 solving baselines, `run_and_evaluate_all_tasks.py`
   (present in `solving-smolagents` and `solving-smolagents-with-retrieval`)
   automates this end-to-end across all three solving spot-check datasets
   and prints per-dataset accuracy — prefer it, or mirror it into new
   solving baselines, over checking each dataset by hand.

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
