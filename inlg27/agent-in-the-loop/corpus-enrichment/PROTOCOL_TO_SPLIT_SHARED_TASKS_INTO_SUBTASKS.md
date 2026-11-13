# The Protocol to Split a Shared Task into Subtasks with Ground Truth

Usage: *"Please run the protocol in `PROTOCOL_TO_SPLIT_SHARED_TASKS_INTO_SUBTASKS.md` on directory X, writing to directory Y."*

## Background

The Agent in the Loop shared task (see the proposal) asks agents to reproduce three components of a shared-task overview paper, given the participants' notebook papers (and optionally code/runs):

- **UniAgent Task 1**: a textual cross-participant summary of the approaches.
- **UniAgent Task 2**: a structured comparison of the approaches along key characteristics (a table).
- **UniAgent Task 3**: a quantitative/statistical analysis of the participants' results (tabular and, if available, textual appraisal).

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

1. **Read** `metadata.json` and `overview/overview.txt.md` completely. `metadata.json` has a `participants` list (title, authors, team name, code URLs) and `provenance.task_assignment_method`/`confidence` (a previous, possibly heuristic grouping) as a starting point, but verify it. A `paper_id` is the paper's directory name under `papers/`; the `*_path` entries in `metadata.json` are stale (`data/final/...`), so resolve paper locations via the directory names in `X`. The `overview.txt.md` is machine-converted: headings and bullets may be mangled (e.g. `### - text` for list items), and tables may be flattened. If the text is unusable for a passage, consult `overview/overview.pdf` or `overview/figures`.
2. **Count subtasks.** Determine from the overview how many subtasks/tracks the shared task has, with their names (e.g. "Task 1: Argument Retrieval for Controversial Questions"). If there is only one, the count is 1. `overview.is_umbrella` in `metadata.json` being `true` means the overview covers several tracks; expect multiple subtasks.
3. **Assign papers.** For every paper in `papers/` (read at least title, abstract, and the introduction/task section of `paper.txt.md`), determine which subtask(s) it participates in. Cross-check with the participant lists/tables in the overview (team names, paper titles, authors). A paper can belong to several subtasks. Papers that are not participant notebooks (e.g. the overview itself, invited talks) are listed under `excluded`.
4. **Create output** `Y/task_<n>` per subtask, where `<n>` is the number of the subtask as named by the organizers (use `task_1`, `task_2`, ...; if there is only one, `task_1`). Each contains:

```
Y/task_<n>/
├── papers/                      # copies of ALL papers that participate in this subtask
│   └── <paper_id>/ ...
├── subtask-info.json            # see below
├── truth-uniagent-task-1.jsonl  # only if applicable
├── truth-uniagent-task-2.jsonl  # only if applicable
└── truth-uniagent-task-3.jsonl  # only if applicable
```

5. **Ground truth extraction** (from the overview, scoped to this subtask; if the overview treats subtasks jointly, include the passages relevant to this subtask and say so in `notes`):
   - `truth-uniagent-task-1.jsonl`: the overview's textual descriptions of participant approaches. One line per participant paper: `{"id": "<paper_id>", "paper_ids": ["<paper_id>"], "summary": "<verbatim text>", "source_section": "..."}` (`id`/`summary` match the existing `touche-20-task-1-spot-check/manual-paper-summaries.jsonl` convention). If one passage covers several papers jointly, write one line with `id` `group-<k>` and all covered `paper_ids`. If the overview has an overall approach discussion, add a line with `id` `_overall` and `paper_ids` of all papers. Papers the overview does not describe get no line.
   - `truth-uniagent-task-2.jsonl`: structured comparison table(s) of the approaches (e.g. "overview of submitted approaches"). One line per table: `{"id": "...", "caption": "...", "table_markdown": "...", "source_section": "..."}`. Only if such a table exists.
   - `truth-uniagent-task-3.jsonl`: the quantitative result tables (e.g. leaderboards, significance tests) and, if present, the textual appraisal of results: `{"id": "...", "type": "table"|"text", "caption": "...", "content": "<verbatim>", "source_section": "..."}`. Only if applicable.
   - If a component has no counterpart, do not create the file, and state it in `subtask-info.json`.
6. **`subtask-info.json`** (single JSON object):

```json
{"shared_task_id": "...", "subtask": "task_1", "subtask_name": "...",
 "paper_ids": ["..."], "excluded": [{"paper_id": "...", "reason": "..."}],
 "uncertain": [{"paper_id": "...", "reason": "..."}],
 "truth_available": {"uniagent_task_1": true, "uniagent_task_2": false, "uniagent_task_3": true},
 "notes": "..."}
```

7. Also write `Y/overview.json` (once per shared task; if `X` holds several shared tasks, `Y/<task_id>/overview.json`): `{"shared_task_id": "...", "num_subtasks": N, "subtasks": [{"subtask": "task_1", "name": "...", "num_papers": M}], "paper_assignment": {"<paper_id>": ["task_1", ...]}}`.
8. **Validate**: every JSONL line parses; every paper in `X/papers` appears in at least one `paper_ids`, `excluded`, or `uncertain`; each `task_<n>/papers/` matches `paper_ids`; ground-truth text occurs in the overview (spot-check with grep, ignoring whitespace and markdown heading/bullet markers; table cell text may be re-formatted as Markdown but numbers and words must be unchanged); `X` is unchanged.
9. **Report** to the user: number of subtasks, papers per subtask, which ground-truth files exist per subtask, and all `uncertain` papers needing a decision.

## Notes

- The overview paper itself and its extracted ground truth must never be placed into `task_<n>/papers/` (it would leak the reference into agent inputs).
