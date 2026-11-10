# Synthetic Dataset Construction (CLEF'27)

This directory contains structured protocols that a coding agent can run to generate synthetic Task-2 (application-solving) datasets. 

**Attention: This currently only contains some ideas from Maik, we need to go over them multiple iterations to incorporate all ideas that we collected. Please do not yet run this, it is only a very first draft that we need to improve upon.

## Execution environment (mandatory)

> **The protocols must only be executed inside a GitHub Codespace (the repository's dev container), never on a local machine, a shared server, or any other environment to ensure that there is no leakage between test datasets that might be available on our own development machines.**

## Protocols

| Protocol | Application type | Modeled on | Status |
|---|---|---|---|
| [`SYNTHESIZING-BUSINESS-TRIP.md`](SYNTHESIZING-BUSINESS-TRIP.md) | Business trips (`dienstreiseantrag-XX`) | [`business-trip-spot-check`](../../cikm26/datasets/business-trip-spot-check) | Detailed draft |
| [`SYNTHESIZING-EXPENSE-REIMBURSEMENT.md`](SYNTHESIZING-EXPENSE-REIMBURSEMENT.md) | Privately advanced costs (`auslagenerstattung-XX`) | [`task-2-expense-reimbursement-spot-check`](../../cikm26/datasets/task-2-expense-reimbursement-spot-check) | Skeleton |
| [`SYNTHESIZING-PROCUREMENT.md`](SYNTHESIZING-PROCUREMENT.md) | Internal procurement (`beschaffungsantrag-XX`) | [`task-2-procurement-spot-check`](../../cikm26/datasets/task-2-procurement-spot-check) | Skeleton |

## Usage

Each protocol defines three difficulty levels (`easy`, `medium`, `hard`) in its
"Difficulty levels" section. Open a Codespace of this repository, start a coding
agent there, and give it one of the protocols together with the number of
cases and the difficulty:

```
Please run the protocol clef27/synthetic-dataset-construction/SYNTHESIZING-BUSINESS-TRIP.md
to create 100 cases (balanced, 50% accept, 50% reject) that are easy.
```

Parameters (all protocols):

| Parameter | Meaning | Default |
|---|---|---|
| number of cases | Total number of cases to generate | must be given |
| balance | Share of `angenommen` cases; the rest is `abgelehnt` | 50 % |
| difficulty | `easy`, `medium`, or `hard` | must be given |

Output goes to `clef27/synthetic-dataset-construction/work/<type>/<difficulty>/`
(`<type>` is `business-trip`, `expense-reimbursement`, or `procurement`).
Different difficulties and repeated runs never overwrite each other; case ids
are numbered `<prefix>-01 …` per output folder. Re-running the same command
resumes: cases already logged as `accepted` in `generation.log` are skipped.
Odd case counts are rounded so the two labels differ by at most one case.

Generated data stays in `work/` until a human has reviewed it (see the
validation section of each protocol); only then is it moved out.

## Common conventions for all protocols

- Output layout mirrors the spot-check datasets: `inputs/<type>-XX/*.pdf`
  (what a system sees), `decision-trail/` (never given to a system),
  `ground-truth.jsonl`, `README.md` (dataset card with TIRA configuration),
  and a deterministic generator script that rebuilds all PDFs.
- `inputs/` holds **only** documents that exist before the decision. Neither
  file names nor contents in `inputs/` may reveal the label.
- Labels are `angenommen` / `abgelehnt`. The set is balanced; inconsistencies
  count only when material (no reward for nitpicking); *traps* look wrong but
  are allowed by the rules.
- The retrieval corpora of each spot-check dataset are copied without modification.
- All PDFs have a text layer.
- All generated people, institutions, vendors, amounts, and reference numbers are fictitious; IBANs have invalid check digits.
- Predictions format: one JSON object per line, `{"antrag": "...", "result": "..."}`.
- Work case by case, append to a JSON-Lines generation log after every case, and
  be resumable (skip cases already logged as accepted).
- Ground truth is derived from the **machine-readable case spec**, not from
  re-reading the PDFs, so labels cannot drift from the rendered documents.
