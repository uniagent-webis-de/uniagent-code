# The Protocol to Enrich Shared Tasks

Usage with an Agent: *"Please run the protocol in `PROTOCOL_TO_ENRICH_SHARED_TASKS.md` on directory X."*

## Goal

Enrich the information on the collected shared tasks. The input directory `X` is either a single shared-task directory (contains `metadata.json`) or a directory containing many of them (e.g. `inlg27/agent-in-the-loop/corpora`). Process every shared-task directory found directly under `X`.

## Rules

- **Never write into `X`.** Treat it as read-only.
- Do not use Python venvs; if you need tooling, use Docker/an existing devcontainer.
- Before starting, ask the user (via the question tool) for the output path of the results file if it was not given. The results are a single JSON-Lines file (e.g. `enriched-shared-tasks.jsonl`), one JSON object per line (never pretty-printed). Never overwrite an existing file without asking.
- Never guess silently: if something cannot be determined, use `null` / `"unknown"` and say why in the `notes` field. Do not fabricate URLs; only report URLs you found in the provided files or verified by fetching them.

## Input structure

Each shared-task directory looks like:

```
├── clef2001-interactive-cross-language-information-retrieval-the-clef-2001-interactive-track
│   ├── metadata.json
│   ├── overview
│   │   ├── figures
│   │   ├── overview.pdf
│   │   └── overview.txt.md
│   └── papers
```

`metadata.json` contains `task_id`, `venue`, `parent_venue`, `year`, `task_name`, and overview/source information. Directories without a `metadata.json` are skipped and reported to the user.

## Procedure

1. List the shared-task directories in `X`.
2. For each one, read `metadata.json` and `overview/overview.txt.md` (look into `papers/` only if the overview is insufficient). You may fetch URLs from these files to verify data availability.
3. Assess the following:
   - **Data availability**: Is the data publicly available? If so, under which URL(s)? (`data_public`: `true`/`false`/`"unknown"`, `data_urls`: list)
   - **Data size**: Rough estimate of the expected data size, e.g. `<=10MB`, `<=100MB`, `ca. 1GB`, ... Base it on the overview (number of documents/queries/runs etc.) and state the basis in `notes`. Use consistent buckets across all tasks and re-check consolidation at the end (step 5).
   - **Interest scores** (integer 1 = very low … 5 = very high, plus a one-sentence justification each):
     - `interest_inlg`: the INLG community (International Natural Language Generation)
     - `interest_nlp`: the general NLP community
     - `interest_ir`: the general IR community
4. Append one JSON object per task to the output file:

```json
{"task_id": "...", "task_name": "...", "year": 2001, "parent_venue": "CLEF",
 "data_public": true, "data_urls": ["https://..."], "data_size": "<=100MB",
 "interest_inlg": {"score": 2, "justification": "..."},
 "interest_nlp": {"score": 3, "justification": "..."},
 "interest_ir": {"score": 5, "justification": "..."},
 "notes": "..."}
```

5. **Consolidate** at the end: re-read the whole output file and make the `data_size` buckets and the interest scores consistent across tasks (similar tasks get similar values); rewrite the file accordingly.
6. Validate that every line parses as JSON, that every processed `task_id` appears exactly once, and that `X` is unchanged (`git status` shows no changes there).
7. Report to the user: number of tasks processed, skipped directories, and tasks with unknown data availability.

