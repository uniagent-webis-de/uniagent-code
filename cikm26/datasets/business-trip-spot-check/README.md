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
      minimum_lines: 5
  baseline:
    link: "../../baselines/business-trip-always-rejected"
    command: "/predict.py --input $inputDataset --output $outputDir"
    format:
      name: "*.jsonl"
      config:
        id_field: "antrag"
        value_field: "result"
        required_fields: ["antrag", "result"]
        minimum_lines: 5
        re_map:
          abgelehnt: 0
          angenommen: 1
  evaluator:
    measures: ["accuracy"]
    image: "ghcr.io/uniagent-webis-de/uniagent-cikm-evaluator:0.0.1"
    command: "/evaluate_submission.py --predictions $inputRun --truths $inputDataset --task solving --output $outputDir"
---

# Business Trip Application — Example Set (Solving)

**All people, departments, trips, companies, amounts, reference numbers, bank
and contact details in this folder are fictitious.** Structure, document types,
and the rule set are modeled on real (pseudonymized within the UNIAGENT
project) business-trip cases from the University of Kassel; however, no real
person or case data is contained. The department/institute details (FB 16,
Wilhelmshöher Allee 71-73) are real, public address data of the university —
the people and departments appearing alongside them are not. The IBAN check
digits are deliberately invalid, so they cannot correspond to any real
account. The set is cleared for publication.

## Task

For each case under `inputs/dienstreiseantrag-XX/` there is a submitted
"Antrag auf Dienstreisegenehmigung" (business trip approval request) along
with its supporting documents (tickets, invoices, booking confirmations,
email correspondence). The task is to check the application for
**completeness and rule compliance** and decide: **angenommen** (accepted) or
**abgelehnt** (rejected). If rejected, it should be possible to state what is
missing or does not comply with the rules.

## Structure

```
dienstreiseantrag-solving/
  README.md
  make_examples.py            # regenerates all PDFs reproducibly
  ground-truth.jsonl          # gold answer per case
  inputs/
    dienstreiseantrag-01/     # 4 PDFs — what the agent sees
    dienstreiseantrag-02/     # 4 PDFs
    dienstreiseantrag-03/     # 3 PDFs
    dienstreiseantrag-04/     # 4 PDFs
    dienstreiseantrag-05/     # 4 PDFs
    retrieval-corpora/        # background corpora for looking up rules
      hessian-law-de/documents.jsonl.gz
      university-kassel-public-de/documents.jsonl.gz
      university-kassel-public-en/documents.jsonl.gz
  decision-trail/             # NOT given to the agent
    dienstreiseantrag-01/     # decision document (evidence for the gold label)
    ...
```

`inputs/` contains exclusively documents that are available **before** the
decision — so it does not reveal the answer. The approval, correction, or
rejection emails live separately in `decision-trail/`; they evidence the gold
label and support traceability (analogous to `gold_status:
evidenced_in_corpus` in `working/tira-dataset/`).

All 24 PDFs have a text layer (`pdftotext -layout` returns text); there are
no image-only documents.

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

| # | Case | Result | Rejection/check pattern |
|---|---|---|---|
| 1 | `dienstreiseantrag-01` | abgelehnt | Application submitted only after the trip took place — no prior approval |
| 2 | `dienstreiseantrag-02` | angenommen | Regular conference trip, complete, on time, talk documented |
| 3 | `dienstreiseantrag-03` | abgelehnt | Return trip not documented, mandatory abroad field empty, date before trip start |
| 4 | `dienstreiseantrag-04` | angenommen | Private follow-on stay > 5 working days, but costs correctly separated |
| 5 | `dienstreiseantrag-05` | abgelehnt | Double cost coverage — scholarship covers the same items |

The check patterns in column 4, as well as the rules used in the set
(6-month exclusion period, €80 domestic overnight allowance limit, foreign
overnight allowance, 5-working-day rule for private stays, A1 certificate
with 8 weeks' lead time, train/flight price comparison, invoice addressee
must be the university, non-reimbursement of evening programs) are derived
from the anonymized analysis of
`annotation_dienstreisen_combined_260528.xlsx` and the business trip approval
in the pseudonymized corpus. The cases themselves are newly written.

Cases 3 and 5 require reading two documents against each other (application
vs. attachment) or recognizing a contradiction within the form itself; case 4
is deliberately a *trap*: the conspicuous feature (long private stay) is
handled in compliance with the rules, so the application should be approved.

## Regenerating

```bash
python make_examples.py
```

Requires `reportlab`. Running it overwrites `inputs/` and `decision-trail/`.

## TIRA Configuration

The TIRA configuration publishes exclusively the content of `inputs/` as the
system input. `decision-trail/` and `ground-truth.jsonl` are packaged together
as private ground truth and provided only to the evaluator.

Systems write `predictions.jsonl` with exactly one line per application:

```json
{"antrag": "dienstreiseantrag-01", "result": "abgelehnt"}
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
  --path business-trip-spot-check \
  --task uniagent-2026 \
  --split train \
  --dry-run
```

Once the baseline is available at the configured GitHub path, the same
command without `--skip-baseline` additionally checks build, execution,
output format, and evaluation.
