---
configs:
- config_name: inputs
  data_files:
  - split: train
    path: "inputs/**"
- config_name: truths
  data_files:
  - split: train
    path:
    - "decision-trail/**"
    - "ground-truth.jsonl"

tira_configs:
  resolve_inputs_to: "inputs"
  resolve_truths_to: "."
  default_upload_name: "predictions.jsonl"
  input_format:
    name: "arbitrary"
  truth_format:
    name: "*.jsonl"
    config:
      id_field: "antrag"
      value_field: "result"
      required_fields: ["antrag", "result"]
      minimum_lines: 8
  baseline:
    link: "../../baselines/business-trip-always-rejected"
    command: "/predict.py --input $inputDataset --output $outputDir"
    format:
      name: "*.jsonl"
      config:
        id_field: "antrag"
        value_field: "result"
        required_fields: ["antrag", "result"]
        minimum_lines: 8
        re_map:
          abgelehnt: 0
          angenommen: 1
  evaluator:
    image: "ghcr.io/uniagent-webis-de/uniagent-cikm-evaluator:0.0.1"
    command: "/evaluate_submission.py --predictions $inputRun --truths $inputDataset --task solving --output $outputDir"
---

# Reimbursement of Privately Advanced Costs — Spot-Check Set (Solving)

**Everything in this folder is fictitious**: people, universities, departments, companies,
places, amounts, reference numbers, bank and contact details. Nothing is taken from a real
document. The set imitates the real UNIAGENT cases in structure and quality: the
universities appear under pseudonyms (`Universität Wernstadt`, `Technische Hochschule
Sallstedt`), vendors and hotels sit all over Germany, documents come from many different
systems, and the typical traces of pseudonymization are there (a town with the postcode of
another region, odd numbers in institutional details, a replaced word in another font,
removed logos, blacked-out signatures, a product line that became a name). These traces
never decide a case. IBANs have wrong check digits and bank codes that are not assigned.

The Wernstadt cases follow the rules of the University of Kassel and the Hessian
Reisekostengesetz, both in the retrieval corpora, as the pseudonymized University of
Kassel cases of the full set do. The Sallstedt cases fall under another state's travel
law, which is not in the corpora; they are decided on the documents alone.

## Task

This set covers reimbursement of privately advanced costs, one of the three task areas of UNIAGENT 2026; the other two have
spot-check sets of the same size: [`business-travel-spot-check`](../business-travel-spot-check), [`procurement-spot-check`](../procurement-spot-check). Each case under `inputs/auslagenerstattung-XX/` is the receipts of a privately advanced expense, as they reach the finance office, without an application form.

The task is to check each case for **completeness and rule compliance** and decide:
**angenommen** (accepted) or **abgelehnt** (rejected). If rejected, it should be possible
to state what is missing or does not comply with the rules.

## Structure

```
expense-reimbursement-spot-check/
  README.md
  ground-truth.jsonl          # gold answer per case
  inputs/
    auslagenerstattung-01/ … -08/   # the documents — what the agent sees
    retrieval-corpora/        # background corpora for looking up rules
      hessian-law-de/documents.jsonl.gz
      university-kassel-public-de/documents.jsonl.gz
      university-kassel-public-en/documents.jsonl.gz
  decision-trail/             # NOT given to the agent: decision documents, where the
                              # real process produces them
```

`inputs/` contains only documents that exist **before** the decision. All PDFs have a text
layer.

## Retrieval Corpora

`inputs/retrieval-corpora/` does not provide case material, but background
corpora that an agent can use to look up individual rules (e.g., overnight
allowance limits, A1 certificate, responsibilities) via retrieval instead of
from the prompt. Each corpus is a `documents.jsonl.gz` with one JSON object
per line (fields include `doc_id`, `url`, `title`, `content`/`text`):

| Folder | Content | Documents | Fields |
|---|---|---|---|
| `hessian-law-de/` | Public crawl of hessenrecht.hessen.de (rulings, decisions, etc.), German | 2,829 | additionally `document_type`, `court`, `decision_date`, `file_number`, `ecli` |
| `university-kassel-public-de/` | Public web crawl of the University of Kassel, German-language pages | 30,983 | additionally `language` |
| `university-kassel-public-en/` | Public web crawl of the University of Kassel, English-language pages | 24,171 | additionally `language` |

These are the same corpora as in the separate retrieval datasets
`../retrieval-hessian-law-de-spot-check/`, `../retrieval-de-spot-check/`, and
`../retrieval-en-spot-check/` (identical `documents.jsonl.gz`); here they
serve as a reference for the business trip check rather than as a retrieval
benchmark in their own right (no queries/qrels included).

The final test set may include additional or larger corpora that are not yet
included here (as of the spot-check) — in particular a crawl of the
University of Kassel **intranet** (e.g., internal travel-expense/business-trip
policies that are not publicly accessible). Agents should therefore not assume
that the set of `retrieval-corpora/` subfolders listed above is exhaustive.

## Cases

| # | Case | Result | Check pattern |
|---|---|---|---|
| 1 | `auslagenerstattung-01` | angenommen | English marketplace invoice (seller in Utrecht) for a specialist book, billed to the university, delivered to the chair: complete |
| 2 | `auslagenerstattung-02` | angenommen | *Trap:* till receipt with article numbers only, keyword written on it by hand (allowed by the reimbursement rule) |
| 3 | `auslagenerstattung-03` | abgelehnt | Invoice for headphones to a private person at a private address, no university reference anywhere: not a reimbursable purchase |
| 4 | `auslagenerstattung-04` | abgelehnt | Pro-forma document (explicitly not an invoice) stamped paid, the final invoice is missing: no valid receipt |
| 5 | `auslagenerstattung-05` | angenommen | Two print-shop invoices and a credit note for misprinted posters; the net amount (invoices minus credit) is claimed: complete |
| 6 | `auslagenerstattung-06` | abgelehnt | The same marketplace order invoiced twice under two invoice numbers, both invoices submitted: duplicate claim |
| 7 | `auslagenerstattung-07` | abgelehnt | Kettle, mugs, coffee and tea for the chair's tea kitchen; two product lines show a person's name instead of a description: not reimbursable either way |
| 8 | `auslagenerstattung-08` | angenommen | *Trap:* online-conference fee in USD claimed as a privately advanced cost with receipt and card statement, the prescribed route for it |

Balanced: 4 angenommen,
4 abgelehnt. Inconsistencies only count when
they are material, so an agent is not rewarded for nitpicking; *traps* look wrong but are
allowed by the rules.

## Regenerating

The documents are generated by `generator/make_examples.py` in the `spot-check-creation`
folder of the UNIAGENT project repository (not part of the published dataset).

## TIRA Configuration

The TIRA configuration publishes exclusively the content of `inputs/` as the
system input. `decision-trail/` and `ground-truth.jsonl` are packaged together
as private ground truth and provided only to the evaluator.

Systems write `predictions.jsonl` with exactly one line per application:

```json
{"antrag": "auslagenerstattung-01", "result": "abgelehnt"}
```

Valid values for `result` are `angenommen` and `abgelehnt`. Accuracy is
evaluated via TIRA's Hugging Face evaluator.

The preliminary baseline in `../../baselines/business-trip-always-rejected/`
predicts `abgelehnt` for every application.

The advanced baseline in `../../baselines/business-trip-smolagents/` uses
smolagents tools for listing, reading, and searching PDFs, looking up policies,
and checking dates, amounts, overlaps, and required fields deterministically
before an `OpenAIModel` makes the decision. It is documented as a separate code submission
because it requires an OpenAI-compatible endpoint and forwarded credentials;
the credential-free preliminary baseline therefore remains the dataset-card
default.

The local packaging can be checked without upload and without a baseline:

```bash
tira-cli dataset-submission \
  --path task-2-expense-reimbursement-spot-check \
  --task uniagent-2026 \
  --split train \
  --dry-run
```

Once the baseline is available at the configured GitHub path, the same
command without `--skip-baseline` additionally checks build, execution,
output format, and evaluation.
