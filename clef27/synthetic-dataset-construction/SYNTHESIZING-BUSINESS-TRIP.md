# Synthesizing Business-Trip Applications (Solving)

> **Execute this plan only inside a GitHub Codespace of this repository** (see
> [`README.md`](README.md#execution-environment-mandatory)). Never run it
> locally or elsewhere, never bring real case material into the Codespace, and
> run all code in Docker / the dev container, not in a virtualenv.

**Parameters** (see [`README.md`](README.md#usage)): number of cases `N`,
share of `angenommen` (default 50 %), and difficulty (`easy`, `medium`,
`hard`, defined below).

## Background

[`cikm26/datasets/business-trip-spot-check`](../../cikm26/datasets/business-trip-spot-check)
contains five fictitious business-trip cases (`dienstreiseantrag-XX`). Each is a
bundle of PDFs (SAP-style "Antrag auf Dienstreisegenehmigung", tickets, hotel
invoices, booking confirmations, e-mail print-outs, bank statement extracts)
that a system must classify as **angenommen** or **abgelehnt**. The gold label
is evidenced by a decision document stored separately in `decision-trail/`.

The existing set is rendered by `make_examples.py` (reportlab) and its cases
cover these patterns:

| Case | Result | Pattern |
|---|---|---|
| 01 | abgelehnt | Application submitted after the trip (no prior approval) |
| 02 | angenommen | Regular, complete, timely conference trip |
| 03 | abgelehnt | Return trip undocumented, mandatory abroad field empty, end date before start |
| 04 | angenommen | *Trap:* private stay > 5 working days, but costs correctly separated |
| 05 | abgelehnt | Double financing (scholarship covers the same items) |

This plan scales that construction to a larger synthetic set while keeping the
same document quality, rule set, label semantics, and file layout.

## Task

Generate `N` new, fully fictitious business-trip cases of the requested
difficulty (default: balanced, 50 % angenommen / 50 % abgelehnt) in
`clef27/synthetic-dataset-construction/work/business-trip/<difficulty>/`, with:

```
work/business-trip/<difficulty>/
├── case-specs/                  # machine-readable source of truth, one JSON per case
│   └── dienstreiseantrag-XX.json
├── generator/                   # deterministic renderer (Dockerfile, requirements.txt, make_examples.py, tests)
├── inputs/
│   ├── dienstreiseantrag-XX/*.pdf
│   └── retrieval-corpora/       # unmodified copy of the spot-check corpora (see "Retrieval corpora")
├── decision-trail/
│   └── dienstreiseantrag-XX/*.pdf
├── ground-truth.jsonl
├── generation.log               # JSON Lines, see below
└── README.md                    # dataset card (copy and adapt the spot-check card incl. TIRA config)
```

### Rule catalogue

The rules are those already used by the spot-check set (derived from the
public University of Kassel / Hessian Reisekostengesetz material in the
retrieval corpora). Every case spec must reference rules by these ids so the
label is auditable. Verify each rule against the retrieval corpora (search the
public corpora in `cikm26/datasets/*-spot-check/documents.jsonl.gz`) before
using it; if a rule cannot be found there, mark it `"source": "unverified"` and
flag it for human review rather than inventing a source.

| Id | Rule | Violation → typically |
|---|---|---|
| `R01-prior-approval` | Trip must be approved **before** it starts; retroactive approval only via exception procedure with department-head statement | abgelehnt |
| `R02-exclusion-period` | 6-month exclusion period for requesting after the fact / applications beyond the allowed horizon | abgelehnt |
| `R03-business-interest` | Dienstliches Interesse documented (invitation, acceptance, programme) | abgelehnt if missing |
| `R04-abroad-field` | Mandatory field "Reise ins Ausland" filled; abroad trips need approval by Personal und Organisation | abgelehnt if empty/inconsistent |
| `R05-a1-certificate` | A1 certificate for EU trips applied for with ≥ 8 weeks lead time | abgelehnt if missing/late |
| `R06-overnight-limit-domestic` | Domestic hotel night ≤ €80 without justification | abgelehnt if exceeded unjustified |
| `R07-overnight-limit-abroad` | Foreign overnight allowance limits per country | abgelehnt if exceeded unjustified |
| `R08-private-stay` | Private stay > 5 working days: only business-caused costs claimable, costs must be separated | angenommen if separated, abgelehnt if not |
| `R09-price-comparison` | Train/flight price comparison provided where required | abgelehnt if missing |
| `R10-invoice-addressee` | Invoices addressed to the university; private addressee needs a replacement voucher ("sachlich richtig") | abgelehnt if not |
| `R11-no-evening-program` | Evening programmes / conference dinners not reimbursable | angenommen if not claimed, abgelehnt if claimed |
| `R12-double-financing` | No double coverage by third-party funds/scholarships | abgelehnt if overlapping |
| `R13-completeness` | All legs documented, totals computed, dates consistent (start ≤ end, end of business ≥ start) | abgelehnt if not |
| `R14-funding-source` | Cost centre / project named and plausible | abgelehnt if missing |

Rules may be added only after verification as above; record additions in the
generation log header.

### Case-spec schema

One JSON per case; the renderer and the ground truth are generated from it.

```json
{
  "antrag": "dienstreiseantrag-06",
  "seed": 6,
  "label": "abgelehnt",
  "difficulty": "medium",
  "kind": "violation",
  "field": "computer science",
  "conference": {"name": "...", "scope": "international", "venue": "...", "source": "https://..."},
  "rules_checked": ["R01-prior-approval", "R10-invoice-addressee"],
  "rules_decisive": ["R01-prior-approval"],
  "traps": [],
  "traveller": {"name": "...", "position": "...", "department": "..."},
  "trip": {"destination": "...", "country": "...", "start": "2027-03-09", "end": "2027-03-11", "purpose": "..."},
  "application": {"submitted": "2027-02-01", "fields": {"reise_ins_ausland": true, "finanzierung": "..."}},
  "documents": [{"file": "antrag-dienstreisegenehmigung.pdf", "template": "sap-antrag", "data": {}}],
  "decision": {"template": "genehmigt|korrekturbedarf|email-rueckfrage", "date": "2027-02-08"},
  "begruendung": "Short German rationale (3–5 sentences, ASCII-umlaut style like the spot-check set).",
  "belege": ["antrag-dienstreisegenehmigung.pdf", "..."]
}
```

`kind` is one of `clean-accept`, `trap-accept`, `violation` (single decisive
rule), `multi-violation` (two or more), `cross-document` (violation only
visible by comparing two documents).

### Research field and conference selection

Every case is anchored in a real academic context so that trips are realistic
and varied:

1. **Select a research field** (e.g. biology, computer science, physics,
   chemistry, mathematics, mechanical/civil/electrical engineering, medicine,
   psychology, economics, law, sociology, education, history, linguistics,
   literature, art/design, architecture, agricultural science, environmental
   science). Fields are assigned centrally in step 0, **balanced across the
   cases** (each field appears ⌊N / #fields⌋ or ⌈N / #fields⌉ times, jointly
   balanced with the label so that no field is mostly accepted or rejected).
   The traveller's department, position, and trip purpose must fit the field.
2. **Search for a real, public conference** of that field, alternating
   `international` and `national` (German) events (≈ 50 / 50 overall, also
   balanced per field where possible; abroad/EU/non-EU destinations follow from
   it). Use web search with generic queries only (field + "conference" +
   year/location); never put any case content, names, or reference material
   into a query. Pick a conference series that recurs, with a plausible
   venue city. If web search is unavailable, use a curated list the agent
   writes from its own knowledge and flags `"source": "from-memory"`.
3. **Plan the trip to that conference**: venue city, plausible dates in the
   fictitious academic year, travel mode and route, hotel in the city,
   registration fee, and the business interest (accepted paper/poster,
   invited talk, workshop, session chair, project meeting at the conference).
   Real conference names and cities are public facts and may appear; **all
   other details are invented** (registration numbers, the traveller, the
   acceptance e-mail, prices, bookings). Do not copy conference text, logos, or
   brochures; write own text.
4. **Record** the field, conference name, scope (`international`/`national`),
   venue, and source URL (or `from-memory`) in the case spec (`field`,
   `conference`). Do not reuse the same conference for more than ~10 % of the
   cases of a run.
5. A trip not tied to a conference (project meeting, archive visit,
   fieldwork) is allowed only for the `purpose` variety targets below, still
   with a field and a real, public destination institution or site.

### Difficulty levels

The difficulty describes how hard it is for a system to reach the right
decision. It is controlled by the spec fields below; the blind check (step 6)
reports whether a system actually sees the case as intended.

| Aspect | `easy` | `medium` | `hard` |
|---|---|---|---|
| Documents per case | 3–4, no noise | 4–5, ≤ 1 irrelevant | 5–6, ≥ 1 irrelevant or distracting (e.g. unrelated booking, outdated draft) |
| Defect family in `abgelehnt` cases (`kind`) | one, visible in the application form alone (`violation`) | one, needs one supporting document (`violation`) | two or more, or only visible by comparing documents (`multi-violation`, `cross-document`) |
| Traps among `angenommen` cases (`trap-accept`) | none: `clean-accept` only | ≈ 25 % | ≥ 50 %, including traps that require a rule lookup |
| Rule knowledge | stated on the form or common sense | one rule from the catalogue, findable in the corpora | several rules; at least one needs retrieval (thresholds, abroad allowances, exceptions) |
| Arithmetic | trivial, totals visible | sums across documents | currency/rates, partial costs, separated private/business shares |
| Layout/noise | clean text layer, standard SAP form | varied templates | varied templates, mixed languages (DE/EN), scan-like layout with text layer, e-mail threads |

Every case must satisfy the row for its level; a case that is easier or harder
than requested is re-specified, not kept.

### Diversity targets (scaled to `N`, within the requested difficulty)

- Label: as requested (default half/half; odd `N` differs by one).
- `trap-accept`: share per the difficulty table (conspicuous feature that is actually compliant, e.g. long
  private stay with separated costs, evening programme mentioned but not
  claimed, private-addressee invoice with replacement voucher attached,
  third-party funding correctly deducted, price above €80 with written
  justification).
- `cross-document`: ≥ 20 % of rejections in `hard`, none in `easy` (e.g. application dates vs. ticket dates, amount in
  form vs. invoice, funding in form vs. scholarship letter).
- Rejections spread over the rules usable at the requested difficulty (no
  rule is the decisive reason for more than 25 % of rejections; with
  `N ≥ 40`, every usable rule appears at least once).
- Domestic ≈ 60 %, EU/abroad ≈ 40 %; trip purposes: conference, workshop,
  project meeting, fieldwork/archive visit, teaching/guest lecture, keynote.
- Modes of transport: train, plane, car (private car with mileage), mixed.
- Traveller roles: doctoral researcher, postdoc, professor, student assistant.
- PDFs per case and noise as in the difficulty table, 1–3 pages each; the
  document set varies per case (no fixed set that predicts the label).
- Dates fall in a single fictitious academic year; no real-person names; use
  generated names and the pseudonymous institutions of the existing sets
  (`Universität Wernstadt`, `Technische Hochschule Sallstedt`) in addition to
  the (public) University of Kassel department/address details already used
  in the spot-check set. Wernstadt cases follow Kassel/Hessian rules;
  Sallstedt cases follow a different state's law and are decided on the
  documents alone (≤ 15 % of cases).

### Procedure (per case)

0. **Set up (once per run).** Read the parameters, create
   `work/business-trip/<difficulty>/` if missing, copy the retrieval corpora
   unmodified, read `generation.log` to find accepted cases (resume), and
   fix the diversity matrix for the remaining cases, including the balanced
   assignment of research field and national/international scope; select the
   conferences here (centrally, so subagents don't pick the same one).
1. **Plan the case.** Pick the next unfilled cell of the diversity matrix
   (label × kind × decisive rule × research field × conference × traveller role) so the
   targets above are met. Choose a new seed
2. **Write the case spec** (schema above, with `"difficulty"` added) including `begruendung` and the
   list of `belege` that evidence it. For `trap-accept` cases the spec must
   name the trap (`traps: ["private-stay-separated"]`) and the rule that makes
   it compliant.
3. **Check consistency of the spec (before rendering).**
   - Re-derive the label from the rules: exactly the `rules_decisive` are
     violated for `abgelehnt`; no rule is violated for `angenommen`.
   - Dates, amounts, and totals are arithmetically correct everywhere except
     where the violation is intended; nights × rate = hotel total; the
     application's total equals the sum of its positions.
   - There is **exactly one intended defect family** per `violation` case
     (two or three for `multi-violation`); no accidental additional defects
     that would make the label ambiguous. Flag ambiguity instead of keeping it.
4. **Render** the PDFs with the generator (extend `make_examples.py`'s
   helpers: `kv_table`, `money_table`, the SAP-form, invoice, booking,
   e-mail and bank-statement templates). Randomise layout, fonts-within-set,
   vendor names, invoice numbering schemes, and date formats per case so no
   template is a label leak. Write decision documents to `decision-trail/`
   only.
5. **Verify the rendering** (see Validation): extract text with
   `pdftotext -layout` and confirm every fact the label depends on is present
   and consistent with the spec.
6. **Independent blind check.** Spawn a fresh subagent that receives **only**
   `inputs/<case>/` plus the rule catalogue (no spec, no ground truth, no
   decision trail) and must return `angenommen`/`abgelehnt` with the rules it
   cites. Record its answer in the log. If it disagrees with the spec label,
   revise the case (fix the ambiguity) and re-run the blind check once; if it
   still disagrees, mark the case `needs_human_review` rather than silently
   keeping or dropping it.
7. **Append to `generation.log`** and move on. Skip cases already logged as
   `accepted` when resuming.

Batching by case or parallelising across cases (one subagent per case) is
fine; the diversity matrix assignment (step 1) is done once, centrally, before
fan-out so subagents do not collide on case ids or seeds.

### Retrieval corpora

Copy the three `retrieval-corpora/` folders (`hessian-law-de`,
`university-kassel-public-de`, `university-kassel-public-en`) of
`cikm26/datasets/business-trip-spot-check/inputs/` **unmodified** (verify with
checksums) into `inputs/retrieval-corpora/`. A rule used in a
case must be findable in them, or be explicitly labelled "decided on the
documents alone" (Sallstedt cases).

### Outputs

**`case-specs/dienstreiseantrag-XX.json`**: schema above, one per case, the
single source of truth.

**`ground-truth.jsonl`**: one line per case, same fields as the spot-check set
(`antrag`, `result`, `begruendung`, `belege`), generated **from the specs**,
sorted by `antrag`. No pretty-printing.

**`generation.log`**: JSON Lines, one object per case:

```json
{"antrag": "dienstreiseantrag-06", "label": "abgelehnt", "difficulty": "medium", "kind": "violation", "rules_decisive": ["R01-prior-approval"], "traps": [], "n_pdfs": 4, "blind_check": "abgelehnt", "blind_rules": ["R01-prior-approval"], "status": "accepted", "reason": "One short sentence."}
```

`status` is `accepted` or `needs_human_review`. Also log, as separate lines
with `"type": "flag"`, any rule marked `unverified`, any case whose blind check
disagreed, and anything that looks like possible leakage (see below).

### Validation (run before finishing, inside Docker)

- Generator unit tests (`test_make_examples.py`) pass via the generator's
  Dockerfile (`docker build` + `docker run --entrypoint python … -m unittest`).
- Field balance: counts per field differ by at most one (report, also per
  label); national/international ≈ 50 / 50; no conference used in more than
  ~10 % of cases; every `conference.source` is a URL or `from-memory`, and
  queries sent to web search are logged and contain no case content.
- Every case spec validates against the schema; every `rules_decisive` /
  `rules_checked` id exists in the rule catalogue.
- Re-running the generator from the specs reproduces byte-identical-modulo-
  PDF-metadata text content (compare `pdftotext` output), proving determinism.
- Every PDF in `inputs/` has a text layer (`pdftotext -layout` non-empty).
- `ground-truth.jsonl` and `generation.log` parse line by line; each
  `antrag` has an `inputs/` folder, a spec, a log line, and (where the
  decision exists) a `decision-trail/` folder.
- **No label leakage:** no file under `inputs/` has a name or text containing
  decision words (`genehmigt`, `abgelehnt`, `angenommen`, `korrekturbedarf`,
  `Rückfrage`, `Ablehnung`) except where they naturally occur in third-party
  documents; PDF metadata (title/author/subject/creator) is empty; file-name
  sets and page counts do not predict the label (report a simple
  classifier-free check: label distribution per file-name and per page-count).
- **No real data:** the generator and the specs contain no names/addresses
  except the public university address data already used in the spot-check
  set; all IBANs fail the check-digit test. No real-data denylist is used
  (real data must never be in the Codespace); instead the agent confirms in
  the log header that no real files were read.
- Balance and diversity report: number of cases per label, `kind`, decisive
  rule, trap, country/domestic, transport, role; all targets above met (or
  deviations explained). Difficulty check: every case matches its row of the
  difficulty table; the blind-check accuracy per difficulty is reported
  (expected to decrease from easy to hard; if `easy` is not near 100 % the
  cases are ambiguous).
- Retrieval corpora checksums equal those in the spot-check dataset.
- Baselines sanity check (inside Docker): `solving-always-rejected` scores
  ≈ 50 %, `solving-always-allow` ≈ 50 %; report both. Optionally run
  `solving-smolagents` on a sample to confirm the set is neither trivial nor
  broken.
- Human review: a person reviews at least all `needs_human_review` cases, all
  `trap-accept` cases, and a 20 % random sample of the rest, and signs off in
  the dataset card before the folder is moved out of `work/`.

### Dataset card

Copy the spot-check `README.md`, adapt: case table (generated from the specs),
counts, the statement that all data is fictitious and synthetically generated
(and how: this plan + generator), the `tira_configs` block (same
`id_field: antrag`, `value_field: result`, `re_map`, evaluator), and the
`tira-cli dataset-submission --path … --task … --split … --dry-run` check.
Update the "Regenerating" section to the Docker command for the generator.

### Open questions to resolve before the first run

- Train/test split across difficulties.
- Whether blind-check subagents may use the retrieval corpora for `medium`/`hard`.
- Whether the intranet-derived rules (not public) are to be modelled; if so
  they must be supplied as an **abstract rule list**, never as source
  documents.
- Language: German only (as in the spot-check set), or additional English
  variants.
