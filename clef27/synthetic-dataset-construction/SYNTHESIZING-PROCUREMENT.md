# Synthesizing Internal-Procurement Cases (Solving) — DRAFT

> **Execute this plan only inside a GitHub Codespace of this repository** (see
> [`README.md`](README.md#execution-environment-mandatory)). Never run it
> locally or elsewhere, never bring real case material into the Codespace, and
> run all code in Docker / the dev container, not in a virtualenv.

> Draft: structure follows [`SYNTHESIZING-BUSINESS-TRIP.md`](SYNTHESIZING-BUSINESS-TRIP.md),
> which is the reference. Sections marked **TODO** are to be completed once the
> business-trip plan has been exercised.

## Background

[`cikm26/datasets/task-2-procurement-spot-check`](../../cikm26/datasets/task-2-procurement-spot-check)
has 8 fictitious cases (`beschaffungsantrag-XX`): a procurement request, as a
form or an e-mail to the procurement office, with offers, baskets or invoices.
Decide **angenommen** / **abgelehnt**. Existing patterns: three offers and
matching award note; single offer below 1,000 EUR (trap); framework-contract
product bought from a web shop; net total inconsistent with positions; large
order without comparison offers but all items framework-catalogue (trap); only
two offers without reason; award note misstating an offer; e-mail thread where
missing offers are supplied later.

## Task

Generate `N` fictitious cases of the requested difficulty (`easy`,
`medium`, `hard`; default 50/50 balanced; parameters as in
[`README.md`](README.md#usage)) in
`clef27/synthetic-dataset-construction/work/procurement/<difficulty>/` with the same layout
as the business-trip plan.

### Research field and procurement selection

As in the business-trip protocol, each case gets a **research field**
(balanced across cases) and the request is planned around it: the agent
selects, by searching public sources with generic queries only, a realistic
field-typical item (e.g. oscilloscope or workstation for engineering/physics,
microscope or centrifuge for biology, GPU server for computer science,
audio recorder for linguistics, archive scanner for history) with a plausible
price class that fits the case's price tier. Real product categories and
public product lines may be named; vendors, offers, prices, and people are
invented (vendor names fictitious). Record `field` and `item_source` in the
case spec. Details are a TODO: finish after the business-trip protocol is
exercised.

### Difficulty levels

**TODO:** define `easy`/`medium`/`hard` analogous to the table in
[`SYNTHESIZING-BUSINESS-TRIP.md`](SYNTHESIZING-BUSINESS-TRIP.md#difficulty-levels)
(documents per case and noise, number/visibility of defects, share of traps,
rule knowledge needed, arithmetic, layout variety), with case-type specific
criteria.

### Rule catalogue (to verify against the public corpora; mark unverified otherwise)

| Id | Rule |
|---|---|
| `P01-direct-award` | Orders below 1,000 EUR net may be direct awards (one offer suffices) |
| `P02-comparison-offers` | From 1,000 EUR: three written offers; fewer only with documented reason — **TODO** verify thresholds (e.g. 2,500 / 5,000 EUR tiers) |
| `P03-framework-contract` | Framework-contract products must be ordered via the contract/catalogue (e.g. WPS), not web shops; then no comparison offers needed |
| `P04-award-to-cheapest` | Award to the cheapest offer or justified otherwise |
| `P05-arithmetic` | Totals in form, offers, and award note are consistent |
| `P06-award-note-accuracy` | Award note quotes the offers correctly |
| `P07-completeness` | Cost centre, budget, approver, positions, delivery address present |
| `P08-invoice-match` | Partial invoices add up to the chosen offer |

### Procedure (per case)

Identical to the business-trip plan (diversity matrix → spec → rule-derived
label and arithmetic check → render → text-layer check → blind check by a
fresh subagent seeing only `inputs/` → `generation.log`; resumable, one defect
family per case, traps per difficulty level; retrieval corpora copied unmodified). Document types to vary: request forms, offers
in several layouts, web-shop baskets, collective-order e-mails, award notes,
framework-catalogue extracts, partial invoices, e-mail threads.

### Outputs and validation

As in the business-trip plan. Identifier format: `beschaffungsantrag-XX`;
prediction line `{"antrag": "beschaffungsantrag-XX", "result": "angenommen|abgelehnt"}`.

### TODO

- Verify the rule catalogue and thresholds; add intranet-derived rules as
  abstract lists only.
- Decide target size and diversity targets (price tiers, product categories,
  number of offers, e-mail vs. form).
- Dataset card and TIRA configuration (copy from the spot-check set).
