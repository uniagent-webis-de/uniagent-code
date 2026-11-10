# Synthesizing Expense-Reimbursement Cases (Solving) — DRAFT

> **Execute this plan only inside a GitHub Codespace of this repository** (see
> [`README.md`](README.md#execution-environment-mandatory)). Never run it
> locally or elsewhere, never bring real case material into the Codespace, and
> run all code in Docker / the dev container, not in a virtualenv.

> Draft: structure follows [`SYNTHESIZING-BUSINESS-TRIP.md`](SYNTHESIZING-BUSINESS-TRIP.md),
> which is the reference. Sections marked **TODO** are to be completed once the
> business-trip plan has been exercised.

## Background

[`cikm26/datasets/task-2-expense-reimbursement-spot-check`](../../cikm26/datasets/task-2-expense-reimbursement-spot-check)
has 8 fictitious cases (`auslagenerstattung-XX`): receipts of privately advanced
expenses as they reach the finance office, without an application form.
Decide **angenommen** / **abgelehnt**. Existing patterns: valid foreign-language
invoice, till receipt with handwritten keyword (trap), private-addressee
invoice without university reference, pro-forma document instead of invoice,
invoice plus credit note (net claimed), duplicate invoices for one order,
non-reimbursable items (tea kitchen), foreign-currency conference fee (trap).

## Task

Generate `N` fictitious cases of the requested difficulty (`easy`,
`medium`, `hard`; default 50/50 balanced; parameters as in
[`README.md`](README.md#usage)) in
`clef27/synthetic-dataset-construction/work/expense-reimbursement/<difficulty>/` with the
same layout as the business-trip plan (`case-specs/`, `generator/`, `inputs/`,
`decision-trail/`, `ground-truth.jsonl`, `generation.log`, `README.md`).

### Research field and purchase selection

As in the business-trip protocol, each case gets a **research field**
(balanced across cases) and the purchase is planned around it: the agent
selects, by searching public sources with generic queries only, a
field-typical item or service (specialist book from a real publisher or
marketplace category, software/licence, lab consumable, conference or online-
course fee of a real public event, printing of a conference poster, etc.).
Real product categories, publishers, and events may be named; sellers'
invoices, numbers, prices, and people are invented. Record `field` and
`item_source` in the case spec. Details are a TODO: finish after the
business-trip protocol is exercised.

### Difficulty levels

**TODO:** define `easy`/`medium`/`hard` analogous to the table in
[`SYNTHESIZING-BUSINESS-TRIP.md`](SYNTHESIZING-BUSINESS-TRIP.md#difficulty-levels)
(documents per case and noise, number/visibility of defects, share of traps,
rule knowledge needed, arithmetic, layout variety), with case-type specific
criteria.

### Rule catalogue (to verify against the public corpora; mark unverified otherwise)

| Id | Rule |
|---|---|
| `E01-valid-invoice` | A proper invoice (not pro-forma/offer/order confirmation) with seller, date, items, amounts |
| `E02-addressee` | Invoice addressed to the university/chair, or private addressee with university reference |
| `E03-item-description` | Line items are descriptive; names/keywords instead of descriptions are not acceptable (hand-written keyword on till receipts allowed) |
| `E04-business-purpose` | Purchase serves official purposes, not personal or social use |
| `E05-no-duplicate` | Same order not claimed twice |
| `E06-proof-of-payment` | Proof of payment where required (card statement, paid stamp on final invoice) |
| `E07-foreign-currency` | Foreign-currency receipts accompanied by payment evidence in EUR |
| `E08-credit-notes` | Credit notes offset; net amount claimed |
| `E09-reimbursement-route` | Item eligible for the private-advance route (vs. mandatory procurement route) — **TODO** verify against corpora |

### Procedure (per case)

Identical to the business-trip plan (plan the cell in the diversity matrix →
write spec → derive label from rules and check arithmetic → render → verify
text layer → blind check by a fresh subagent seeing only `inputs/` → append to
`generation.log`; resumable, one defect family per case, traps per difficulty level; retrieval corpora copied unmodified).
Document types to vary: marketplace invoices (EN/DE/NL), till receipts, print-
shop invoices, card statements, pro-forma documents, credit notes, conference
receipts, hotel/restaurant slips.

### Outputs and validation

As in the business-trip plan (schema-validated specs, ground truth derived from
specs, determinism, text layer, no label leakage in file names/metadata, no
real data, balance/diversity report, baseline sanity check, human review).
Identifier format: `auslagenerstattung-XX`; prediction line
`{"antrag": "auslagenerstattung-XX", "result": "angenommen|abgelehnt"}`.

### TODO

- Verify the rule catalogue and add intranet-derived rules as abstract lists only.
- Decide target size and diversity targets (vendors, currencies, languages,
  payment methods).
- Dataset card and TIRA configuration (copy from the spot-check set).
