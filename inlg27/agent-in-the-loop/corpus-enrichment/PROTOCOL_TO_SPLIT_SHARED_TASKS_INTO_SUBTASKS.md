# The Protocol to Split a Shared Task into Subtasks with Ground Truth

Usage: *"Please run the protocol in `PROTOCOL_TO_SPLIT_SHARED_TASKS_INTO_SUBTASKS.md` on directory X, writing to directory Y."*

## Target output structure

This is the complete structure of the output `Y` for one shared task. Every entry is tagged: **[input]** may be given to systems (agents) that are evaluated; **[truth]** is bookkeeping/reference and must never be passed to systems. Optional entries are only created if the material exists in `X` (see the steps referenced in the comments).

```
Y/
├── overview.json                                 # [truth] subtasks and paper assignment, step 7
└── task_<n>/                                     # one directory per subtask, step 4
    ├── subtask-info.json                         # [input] task description, no results, step 6a
    ├── papers/                                   # [input] copies of ALL participant papers of the subtask
    │   └── <paper_id>/ (paper.pdf, paper.txt.md, figures, tables)
    ├── code/                                     # [input] optional, step 5b
    │   └── <paper_id>/<repo-name>.zip            #   repository at the evaluated commit, without .git
    ├── code-ai-summary/                          # [input] optional, step 5b2: AI-generated views of the code
    │   ├── README.md                             #   how the summaries were made/obtained, by which model, caveats
    │   └── <paper_id>/ ...                       #   summaries, main snippets, nuggets per paper (and repository)
    ├── runs/                                     # [input] optional, step 5c: submitted runs, organized by paper
    │   ├── README.md                             #   what the material is, provenance, format
    │   ├── <paper_id>/ ...                       #   runs of the team(s) behind that paper
    │   └── _unassigned/ ...                      #   runs without a paper (e.g. organizers' baselines)
    ├── evaluations/                              # [input] optional, step 5c: evaluation results of the runs, same layout
    │   ├── README.md
    │   ├── <paper_id>/ ...
    │   └── _unassigned/ ...
    ├── evaluation-code/                          # [input] optional, step 5d: self-contained evaluator
    │   ├── README.md                             #   provenance (where the code came from), usage, expected formats
    │   ├── Dockerfile, requirements.txt, tests   #   everything needed to run it
    │   └── ...                                   #   reads runs/ + truth-data/, writes evaluations in the layout of evaluations/
    ├── truth-data/                               # [truth] optional, step 5d: gold standards (qrels, ground-truth neighbors, ...)
    │   ├── README.md                             #   provenance and how evaluation-code uses it
    │   └── ...                                   #   without the collection/corpus if it is not needed for evaluation
    ├── overview-paper/                           # [truth] optional, step 5d: copy of X/overview/, used to validate evaluation-code
    │   └── (overview.pdf, overview.txt.md, figures, tables)
    ├── truth-subtask-info.json                   # [truth] bookkeeping, step 6b
    ├── truth-approach-summary.jsonl              # [truth] optional (UniAgent Task 1), step 5
    ├── truth-structured-comparison.jsonl         # [truth] optional (UniAgent Task 2), step 5
    └── truth-quantitative-analysis/              # [truth] optional (UniAgent Task 3), step 5
        ├── analysis-table.jsonl                  #   one run per line, with its evaluation(s) and paper link
        └── analysis-description.txt              #   verbatim description of the results, if any
```

Principles: (1) everything under `Y/task_<n>/` is a copy or derivation, `X` stays untouched; (2) `truth-*` entries, `truth-data/` and `overview-paper/` carry the reference or the evaluation truth and are the only places where overview content or gold standards appear; (3) every optional directory has a `README.md` explaining its content, provenance and how to use it, so an agent or evaluator can continue without the protocol; (4) paths are relative to `Y/task_<n>/` and `paper_id`s are the directory names of `X/papers/`; (5) `runs/` and `evaluations/` are organized by `paper_id`, runs that cannot be linked to a paper go under `_unassigned/<team or run id>/`; (6) `evaluation-code/` is self-contained and reproduces the evaluations in `evaluations/` (and the corresponding numbers of the overview paper) from `runs/` and `truth-data/`.

## Background

The Agent in the Loop shared task (see the proposal) asks agents to reproduce three components of a shared-task overview paper, given the participants' notebook papers (and optionally code/runs):

- **Approach summary** (UniAgent Task 1): a textual cross-participant summary of the approaches.
- **Structured comparison** (UniAgent Task 2): a structured comparison of the approaches along key characteristics (a table).
- **Quantitative analysis** (UniAgent Task 3): a quantitative/statistical analysis of the participants' runs and their evaluations (and, if available, a textual appraisal).

The ground truth is extracted from the organizers' overview paper. It is a *reference*, not a gold standard: extract passages faithfully and do not paraphrase.

A shared task may consist of several subtasks (e.g. "Task 1", "Task 2"); the agent's input is per subtask, so each becomes its own output directory.

## Rules

- **Never write into `X`** (read-only). Ask the user for the output directory `Y` if it was not given; never overwrite existing content in `Y` without asking.
- Do not use Python venvs; use Docker/an existing devcontainer if tooling is needed.
- Copy files, never move them. Do not modify copied papers.
- Extract ground truth **verbatim** from `overview/overview.txt.md` (quote, keep tables as in the source, record the section heading/location). Do not invent content. If a component is absent from the overview, mark it as not applicable rather than synthesizing it.
- Do not guess when uncertain which subtask a paper belongs to: record it in `uncertain` and ask the user at the end.
- JSON-Lines files contain one JSON object per line, never pretty-printed.

## Input structure

`X` is one shared-task directory:

```
X
├── metadata.json
├── README.md                    # optional, see step 1
├── code-repositories.json       # optional, see step 5b
├── runs.json, task<n>.zip, *.h5, truths.json, ...   # optional extra material (runs, evals, evaluation code/gold standards), described by README.md, see steps 5c/5d
├── overview
│   ├── figures
│   ├── overview.pdf
│   └── overview.txt.md
└── papers
    ├── <paper_id_1>   (paper.pdf, paper.txt.md, figures, tables)
    └── <paper_id_2>
```

If `X` contains several shared-task directories (each with `metadata.json`), run the protocol for each separately into `Y/<task_id>/`.

## Procedure

1. **Read** `X/README.md` (if present), `metadata.json` and `overview/overview.txt.md` completely. The README may describe additional material in `X` (AI summaries of the code, runs and their evaluations, evaluation scripts, gold standards, truth links, code repositories) and how to incorporate it; follow it and ask the user if it is unclear or contradictory. `metadata.json` has a `participants` list (title, authors, team name, code URLs) and `provenance.task_assignment_method`/`confidence` (a previous, possibly heuristic grouping) as a starting point, but verify it. A `paper_id` is the paper's directory name under `papers/`; the `*_path` entries in `metadata.json` are stale (`data/final/...`), so resolve paper locations via the directory names in `X`. The `overview.txt.md` is machine-converted: headings and bullets may be mangled (e.g. `### - text` for list items), and tables may be flattened. If the text is unusable for a passage, consult `overview/overview.pdf` or `overview/figures`.
2. **Count subtasks.** Determine from the overview how many subtasks/tracks the shared task has, with their names (e.g. "Task 1: Argument Retrieval for Controversial Questions"). If there is only one, the count is 1. `overview.is_umbrella` in `metadata.json` being `true` means the overview covers several tracks; expect multiple subtasks.
3. **Assign papers.** For every paper in `papers/` (read at least title, abstract, and the introduction/task section of `paper.txt.md`), determine which subtask(s) it participates in. Cross-check with the participant lists/tables in the overview (team names, paper titles, authors). A paper can belong to several subtasks. Papers that are not participant notebooks (e.g. the overview itself, invited talks) are listed under `excluded`.
4. **Create output** `Y/task_<n>` per subtask, where `<n>` is the number of the subtask as named by the organizers (use `task_1`, `task_2`, ...; if there is only one, `task_1`), with the structure of *Target output structure* above. Start with `papers/`; the other entries follow in the steps below.

5. **Ground truth extraction** (from the overview, scoped to this subtask; if the overview treats subtasks jointly, include the passages relevant to this subtask and say so in `notes`):
   - `truth-approach-summary.jsonl` (UniAgent Task 1): the overview's textual descriptions of participant approaches. One line per participant paper: `{"id": "<paper_id>", "paper_ids": ["<paper_id>"], "summary": "<verbatim text>", "source_section": "..."}` (`id`/`summary` match the existing `touche-20-task-1-spot-check/manual-paper-summaries.jsonl` convention). If one passage covers several papers jointly, write one line with `id` `group-<k>` and all covered `paper_ids`. If the overview has an overall approach discussion, add a line with `id` `_overall` and `paper_ids` of all papers. Papers the overview does not describe get no line.
   - `truth-structured-comparison.jsonl` (UniAgent Task 2): the overview's structured comparison table(s) of the approaches (e.g. "overview of submitted approaches"); a plain team list or results table does not count. One line per table row, as an object with the table's column headers as keys, plus `"table_id"` (e.g. `"Table 4"`) and `"source_section"`. Only if such a table exists.
   - `truth-quantitative-analysis/` (UniAgent Task 3). **Create this directory only if the overview reports runs and their evaluations for this subtask** (per-run or per-team results, e.g. leaderboards; an analysis consisting only of prose without any run-level evaluation does not qualify). Otherwise skip it and state this in `truth-subtask-info.json`.
     - `analysis-table.jsonl`: **one line per run** (a submitted run, or the best run per team/system if that is all the overview reports; include organizers' baseline runs). Merge all result tables of the subtask by run:
       `{"run_id": "<run name as in the overview, else <team>/<algorithm>>", "team": "...", "paper_ids": ["<paper_id>"], "baseline": false, "evaluations": [{"table_id": "Table 3", "rank": 1, "measures": {"recall": "0.8178", "total time (s)": "187.60"}}], "source_section": "..."}`
       - `paper_ids` links the run to the participant paper(s) of that team (from step 3); use `[]` for baseline runs and for teams without a paper in `papers/`, and say so in `notes`.
       - `evaluations` has one entry per evaluation of the run (e.g. different tables or test sets), with measure names as in the table headers and values as strings exactly as in the source. A run with several evaluations has several entries.
       - Runs not ranked, out of competition or not finished keep their row; add `"note"` inside the evaluation entry (e.g. footnotes such as "did not finish").
       Record each source table's caption in `truth-subtask-info.json` under `table_captions`.
     - `analysis-description.txt`: the overview's textual description/appraisal of these results, verbatim, as plain text (paragraphs separated by blank lines). Create it only if such text exists.
   - If a component has no counterpart, do not create the file/directory, and state it in `truth-subtask-info.json`.

   **5b. Code archives** (only if `X/code-repositories.json` exists). It maps `paper_id` to a list of `{"url", "commit", "branch", "tasks"}` (the code repository of the paper's system, the commit evaluated, and the subtasks, named `task1`, `task2`, ..., it was used for). Papers without a public repository have an empty list. If the file is absent, skip this step. Otherwise, after step 4, for each `Y/task_<n>` run (needs `git` and network access; use Docker, e.g. the `python:3.12` image):

   `python corpus-enrichment/create_code_archives.py --repositories X/code-repositories.json --subtask-dir Y/task_<n>`

   The script keeps only papers in `Y/task_<n>/papers/` and repositories whose `tasks` contain `task<n>`, clones each repository, checks out the commit and verifies that `HEAD` is that commit (it fails otherwise), removes all `.git` entries, and writes `Y/task_<n>/code/<paper_id>/<repo-name>.zip`. A branch no longer containing the commit is only a warning. If it fails for a repository (e.g. private or deleted), report it to the user instead of skipping silently. Do not leave the code directory empty: omit it if no archive was created.

   **5b2. AI summaries of the code** (only if `X/README.md` says where to find them, e.g. a directory or archive with AI-summarized variants of the code, main snippets, or nuggets). Copy the material of subtask `<n>` to `Y/task_<n>/code-ai-summary/<paper_id>/...` (organized by the paper id of the repository's paper; never move; do not mix subtasks) and write a `README.md` there: what the files are, how they were produced (model, prompt, source repository and commit, if the README of `X` states it), and that they are AI-generated and may be wrong. Do not generate such summaries yourself, and do not create the directory if `X` does not provide them. They must be consistent with `code/` (same commits); record mismatches under `notes`.

   **5c. Runs and their evaluations** (only if `X/README.md` or `X` describes such material, e.g. per-task `task<n>.zip` with runs/evals, `runs.json`). Follow the README to unpack/copy the material of subtask `<n>` (never move; never mix subtasks):
   - `runs/<paper_id>/...`: the submitted runs of the team(s) behind each paper (link team to paper as in step 3 / the `paper_ids` of `analysis-table.jsonl`). Runs without a paper (organizers' baselines, teams without a paper in `papers/`) go to `runs/_unassigned/<team or run id>/...`.
   - `evaluations/<paper_id>/...` (and `evaluations/_unassigned/...`): the evaluation results of exactly these runs, same layout, in the format given by the source.
   - Write a `README.md` into `runs/` and `evaluations/`: contents, provenance (path in `X`/URL), file formats, and how run and evaluation entries relate (e.g. via a run id). If the source does not say which paper/subtask a run belongs to, record it under `uncertain`/`notes` and ask the user.

   **5d. Evaluation code, truth data and overview paper** (only if `X` provides gold standards and a way to evaluate, e.g. gold-standard files and/or a pointer to an evaluator in `X/README.md`):
   - `truth-data/`: the gold standards of this subtask (qrels, ground-truth neighbors, ...), reduced to what evaluation needs (e.g. drop the indexed collection if it is not required), with a `README.md` on provenance and how it was derived (commands, so it can be repeated).
   - `evaluation-code/`: obtain the evaluator as the README of `X` describes (repository/commit/URL; use `create_code_archives.py` semantics for repositories: pinned commit, no `.git`), or write it if only a description exists, and make it **self-contained**: a `README.md` (provenance incl. exact source and commit, usage, input/output formats), a `Dockerfile` and pinned requirements, no dependency on paths outside `Y/task_<n>/` (it reads `runs/` and `truth-data/`, writes evaluations in the layout of `evaluations/`), and tests where sensible. Prefer the original code over reimplementation; if you must modify it, document every change in the README.
   - `overview-paper/`: copy of `X/overview/` (pdf, txt.md, figures, tables). It is a **[truth]** entry and only serves to validate the evaluation code.
   - **Validate reproduction** (in Docker, never in a venv): run `evaluation-code` on `runs/` with `truth-data/`; compare the result (a) with `evaluations/` and (b) with the corresponding numbers reported in the overview paper (`truth-quantitative-analysis/analysis-table.jsonl`, `table_captions`). Document in `evaluation-code/README.md` the exact command and the outcome (which runs/measures match, tolerances, and which do not, with a reason such as timing measures that depend on hardware). Do not adjust the code or numbers to force a match; report mismatches to the user.

6. **Two info files** per subtask:

   a. **`subtask-info.json`** describes the subtask for systems that are evaluated on it, so it **must not leak** the reference: no results, rankings, winners, or participant approaches. Base it on the task definition in the overview (task/setup sections, dataset, evaluation measures, constraints) and on `metadata.json`:

```json
{"shared_task_id": "...", "subtask": "task_1", "name": "...",
 "description": "Self-contained description of the goal of the subtask: input data, what a solution must produce, evaluation measure and constraints. Several paragraphs are fine.",
 "shared_task_name": "...", "venue": "...", "year": 2026,
 "data": "Short description of the dataset(s) used in the subtask.",
 "evaluation": "Measure(s) and requirements used to evaluate/rank submissions.",
 "source_section": "..."}
```

   `name` is the organizers' name for the subtask. Write the description in your own words from the overview's task definition (this file is not ground truth), in the language of the overview, and do not mention other subtasks' results.

   b. **`truth-subtask-info.json`** (single JSON object; bookkeeping, never passed to systems):

```json
{"shared_task_id": "...", "subtask": "task_1", "subtask_name": "...",
 "paper_ids": ["..."], "excluded": [{"paper_id": "...", "reason": "..."}],
 "uncertain": [{"paper_id": "...", "reason": "..."}],
 "truth_available": {"approach_summary": true, "structured_comparison": false, "quantitative_analysis": true},
 "table_captions": {"Table 3": "..."},
 "notes": "..."}
```

7. Also write `Y/overview.json` (once per shared task; if `X` holds several shared tasks, `Y/<task_id>/overview.json`): `{"shared_task_id": "...", "num_subtasks": N, "subtasks": [{"subtask": "task_1", "name": "...", "num_papers": M}], "paper_assignment": {"<paper_id>": ["task_1", ...]}}`.
8. **Validate**: every JSONL line parses; every paper in `X/papers` appears in at least one `paper_ids`, `excluded`, or `uncertain`; each `task_<n>/papers/` matches `paper_ids`; every `paper_ids` entry in `analysis-table.jsonl` exists in `papers/`; every `code/<paper_id>` has a matching `papers/<paper_id>` and no zip contains a `.git` entry; `code-ai-summary/`, `runs/`, `evaluations/`, `evaluation-code/` and `truth-data/` (if present) contain a `README.md` and only material of this subtask; `runs/` and `evaluations/` entries are under a `paper_id` of `papers/` or `_unassigned/`; the evaluation-code reproduction (step 5d) was run and its outcome documented; ground-truth text occurs in the overview (spot-check with grep, ignoring whitespace and markdown heading/bullet markers; table cell text may be re-formatted as Markdown but numbers and words must be unchanged); `X` is unchanged; `subtask-info.json` contains no results or participant names.
9. **Report** to the user: number of subtasks, papers per subtask, which ground-truth files exist per subtask, which optional entries (`code/`, `code-ai-summary/`, `runs/`, `evaluations/`, `evaluation-code/`, `truth-data/`, `overview-paper/`) exist, the outcome of the evaluation reproduction (what matched, what did not), and all `uncertain` papers/runs needing a decision.

## Notes

- The overview paper itself and its extracted ground truth must never be placed into `task_<n>/papers/`, `runs/`, `evaluations/` or `evaluation-code/` (it would leak the reference into agent inputs); its only copy is `overview-paper/`, tagged **[truth]**.
