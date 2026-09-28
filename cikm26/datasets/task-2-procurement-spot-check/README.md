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
    link: "../../baselines/solving-always-rejected"
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

# Internal Procurement — Spot-Check Set (Solving)

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

This set covers internal procurement, one of the three task areas of UNIAGENT 2026; the other two have
spot-check sets of the same size: [`business-trip-spot-check`](../business-trip-spot-check), [`task-2-expense-reimbursement-spot-check`](../task-2-expense-reimbursement-spot-check). Each case under `inputs/beschaffungsantrag-XX/` is a procurement request, as a form or as an e-mail to the procurement office, with offers, baskets or invoices.

The task is to check each case for **completeness and rule compliance** and decide:
**angenommen** (accepted) or **abgelehnt** (rejected). If rejected, it should be possible
to state what is missing or does not comply with the rules.

## Structure

```
task-2-procurement-spot-check/
  README.md
  ground-truth.jsonl          # gold answer per case
  inputs/
    beschaffungsantrag-01/ … -08/   # the documents — what the agent sees
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
| 1 | `beschaffungsantrag-01` | angenommen | Three offers in three layouts, form and award note agree; the cheapest wins |
| 2 | `beschaffungsantrag-02` | angenommen | *Trap:* only one offer, but the order is below 1,000 EUR (direct award), request by e-mail |
| 3 | `beschaffungsantrag-03` | abgelehnt | Collective order e-mail with 9 shop positions; the monitors come from a web shop although monitors are framework-contract products |
| 4 | `beschaffungsantrag-04` | abgelehnt | Stated net total of the form is 41 % above the sum of its own positions |
| 5 | `beschaffungsantrag-05` | angenommen | *Trap:* 2.971,80 EUR net without comparison offers, but every item is a framework-contract catalogue article ordered through WPS |
| 6 | `beschaffungsantrag-06` | abgelehnt | Order of 2.670,00 EUR net with only two offers and no reason for the missing third |
| 7 | `beschaffungsantrag-07` | abgelehnt | Award note states one offer 38 % above the offer document, which hides that it was the cheapest |
| 8 | `beschaffungsantrag-08` | angenommen | Thread: query for missing comparison offers, reply supplies them; two stamped partial invoices add up to the chosen offer |

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
{"antrag": "beschaffungsantrag-01", "result": "abgelehnt"}
```

Valid values for `result` are `angenommen` and `abgelehnt`. Accuracy is
evaluated via TIRA's Hugging Face evaluator.

The preliminary baseline in `../../baselines/solving-always-rejected/`
predicts `abgelehnt` for every application.

The advanced baseline in `../../baselines/solving-smolagents/` uses
smolagents tools for listing, reading, and searching PDFs, looking up policies,
and checking dates, amounts, overlaps, and required fields deterministically
before an `OpenAIModel` makes the decision. It is documented as a separate code submission
because it requires an OpenAI-compatible endpoint and forwarded credentials;
the credential-free preliminary baseline therefore remains the dataset-card
default.

The local packaging can be checked without upload and without a baseline:

```bash
tira-cli dataset-submission \
  --path task-2-procurement-spot-check \
  --task uniagent-2026 \
  --split train \
  --dry-run
```

Once the baseline is available at the configured GitHub path, the same
command without `--skip-baseline` additionally checks build, execution,
output format, and evaluation.
