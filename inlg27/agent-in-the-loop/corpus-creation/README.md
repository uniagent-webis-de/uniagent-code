# Shared-task corpus builder

This folder builds the corpus for the INLG 2027 agent-in-the-loop task.

Each corpus example has:

```text
Input:  papers written by participating teams
Target: the overview paper written by the task organizers
```

The pipeline downloads public proceedings pages, identifies overview and participant
papers, downloads their PDFs, extracts their contents, and builds a consistent dataset.
It never uploads anything. All generated data stays in the local `data/` directory.

## Quick start

### 1. Open this directory

From the repository root:

```bash
cd inlg27/agent-in-the-loop/corpus-creation
```

### 2. Install the requirements

You need Python 3.10+, Node.js/npm, Java, and SBT. SBT is unnecessary if you already
have an assembled PDFFigures2 JAR. You also need enough disk space for thousands of PDFs
and extracted images.

```bash
python3 -m pip install -r requirements.txt
npm install -g @llamaindex/liteparse
mkdir -p third_party
git clone https://github.com/allenai/pdffigures2.git third_party/pdffigures2
cd third_party/pdffigures2
sbt assembly
cd ../..
```

### 3. Run the tests

The tests use saved examples and do not need internet access:

```bash
python3 -m pytest
```

### 4. Run the complete pipeline

With a local PDFFigures2 checkout:

```bash
python3 src/run_pipeline.py --pdffigures2-dir third_party/pdffigures2
```

Or with an assembled JAR:

```bash
python3 src/run_pipeline.py --pdffigures2-jar /absolute/path/to/pdffigures2.jar
```

The complete run downloads thousands of papers and can take a long time. It is safe to
run the command again: completed downloads and intermediate files are reused.

## Pipeline overview

```text
Configured proceedings URLs
        ↓
Download and cache proceedings HTML
        ↓
Parse task sections and paper metadata
        ↓
Create and screen candidate tasks
        ↓
Merge candidates from all venues
        ↓
Download PDFs for high-confidence tasks
        ↓
Extract Markdown, figures, tables, counts, and code links
        ↓
Build and validate the final corpus
```

## Step 1: Read the configured URLs

The `src/*_config.py` files contain the editions and official URLs:

- `clef_config.py`
- `semeval_config.py`
- `acl_config.py`
- `trec_config.py`
- `ntcir_config.py`
- `fire_config.py`
- `mediaeval_config.py`
- `sisap_config.py`

The URLs were collected from each venue's official archive or proceedings index. “All
years” means all editions listed by those official archives when the configuration was
written. New editions must be added to the configuration.

Current configured coverage:

- CLEF: 2000–2025
- SemEval: 2007, 2010, and 2012–2026 where listed by ACL Anthology. Participant papers of 2007–2015
  have plain titles, so `semeval_legacy_tasks.py` reads each one's first two pages and assigns it to
  a task only when exactly one `SemEval-YYYY Task N` is named (and neighbouring papers agree);
  `provenance.task_assignment_method` is then `first_page_task_mention`
- ACL Anthology shared tasks other than SemEval (CoNLL 2000–2020, IJCNLP 2017, WNUT, CASE,
  WANLP/NADI, NLPTEA, MADAR, and others): the curated tasks in `acl_config.py`, seeded
  from the overview papers listed in `data/raw/martin_22_shared_tasks.json`
- TREC: 1992–2025
- NTCIR: NTCIR-1 through NTCIR-18 (1999–2025)
- FIRE: 2008 and 2010–2025; its archive has no 2009 link
- MediaEval: 2010–2023 and 2025–2026; its history has no 2024 edition
- SISAP Indexing Challenge: 2023–2026

Authoritative sources:

| Collection | Source used to form task groups |
|---|---|
| CLEF | [CEUR-WS](https://ceur-ws.org/) working-note volumes |
| SemEval | [ACL Anthology](https://aclanthology.org/) proceedings |
| ACL Anthology tasks | [ACL Anthology](https://aclanthology.org/) volume pages, curated task by task |
| TREC | [NIST TREC](https://trec.nist.gov/proceedings/proceedings.html) proceedings |
| NTCIR | [NII NTCIR](https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings/index.html) proceedings |
| FIRE | [FIRE](https://fire.irsi.org.in/fire/2025/home) archive and CEUR working notes |
| MediaEval | [MediaEval](https://multimediaeval.github.io/about/) history and CEUR proceedings |
| SISAP | [SISAP challenges](https://sisap-challenges.github.io/) and conference proceedings |

DBLP and TIRA are supplemental checks only. They may confirm metadata, but they never
create a paper or decide which task it belongs to.

## Step 2: Download the proceedings pages

The `fetch_*.py` scripts download and cache HTML under `data/raw/`.

This stage downloads proceedings/index pages, not paper PDFs. Cached pages are reused.
Failures are logged instead of silently ignored.

## Step 3: Parse the proceedings pages

The parsers use Python and BeautifulSoup. No language model is used. They extract:

- task or track headings
- paper titles and authors
- paper roles, when provided by the source
- PDF URLs from the page's actual `href` links

Each venue has a separate parser because its HTML is different. PDF URLs are never
guessed from filename patterns.

## Step 4: Identify overview papers

For CLEF, organizer papers are detected using these title patterns:

```regex
\boverview\b|\bextended abstract\b
^\S+\s+20\d\d\s*[—–-]\s*.*\btask\b\s*$
^The CLEF[- ]20\d\d\b.*\b(?:track|task)\b
^The .+\bTrack at CLEF[- ]?20\d\d$
^Report on CLEF-20\d\d (?:Experiments|Multilingual Tracks)$
```

We created these rules by inspecting real titles, running the parser over all configured
years, and manually reviewing missed or incorrect groups. The rules are deliberately
narrow to avoid treating ordinary participant papers as organizer papers.

Other sources use stronger source structure where available. MediaEval publishes paper
roles, TREC and NTCIR have official track/task sections, and SemEval titles identify task
numbers.

## Step 5: Group papers into candidate tasks

For a CLEF/CEUR section:

1. **One explicit overview:** assign all other papers in the section to it. This is
   normally high confidence.
2. **Multiple overviews:** match papers using title keywords. This is always medium
   confidence and requires review.
3. **No explicit overview:** the first paper may be used provisionally. This is medium
   confidence and requires review.
4. **No participant papers:** reject the candidate.

“Best of Labs” republications are excluded before grouping.

We originally assumed each overview was immediately followed by its participants. Real
CEUR pages often list all overviews first, so multiple-overview sections are never
accepted automatically.

Each source writes its own candidate file:

```text
data/intermediate/candidates/clef.jsonl
data/intermediate/candidates/semeval.jsonl
data/intermediate/candidates/acl.jsonl
data/intermediate/candidates/trec.jsonl
data/intermediate/candidates/ntcir.jsonl
data/intermediate/candidates/fire.jsonl
data/intermediate/candidates/mediaeval.jsonl
data/intermediate/candidates/sisap.jsonl
```

## Step 6: Merge and validate candidates

`merge_candidates.py` combines the source files into:

```text
data/intermediate/all_candidates.jsonl
```

This file contains both high- and medium-confidence candidates. The merger checks for
missing fields or PDF URLs, duplicate task IDs, PDFs assigned to different tasks, and
previous required-PDF download failures.

A failing high-confidence candidate is downgraded to medium. Medium-confidence and
unresolved records are also written to:

```text
data/intermediate/needs_review.jsonl
```

## Step 7: Download the paper PDFs

By default, only high-confidence candidates continue. `download_papers.py` downloads each
overview and all its participant PDFs into:

```text
data/intermediate/downloads/{task_id}/
```

Every file must begin with the PDF signature. A task moves to `data/final/{task_id}/`
only when all its PDFs are valid. One failed required PDF downgrades the task to medium
confidence so it can be reviewed or retried.

## Step 8: Convert PDFs to Markdown

`parse_fulltext.py` uses Liteparse to create:

```text
overview/overview.pdf
overview/overview.txt.md
papers/{paper_id}/paper.pdf
papers/{paper_id}/paper.txt.md
```

If the text layer is too thin to trust, the manifest records:

```json
"needs_ocr": true
```

OCR is optional. To retry only those documents with an OCR server:

```bash
python3 src/parse_fulltext.py \
  --ocr-server-url http://localhost:8080 \
  --only-needs-ocr
```

With no OCR server, `--builtin-ocr` uses liteparse's bundled Tesseract instead (slower, weaker on
tables, English only unless `--ocr-language` is set). A document is also flagged when its text
layer exists but is garbled (a broken font encoding: almost no English function words and no CJK
text), which length checks alone miss.

OCR text is lower fidelity than a PDF text layer (words can be displaced and columns interleaved),
so each document record carries `text_source`: `text_layer` or `ocr`.

**Better OCR (optional stage).** liteparse's bundled Tesseract reads columns and tables badly.
`src/ocr_vlm.py` re-reads those documents with a vision-language OCR model (default
`lightonai/LightOnOCR-3-1B`), which returns Markdown in reading order; its HTML tables are converted
to Markdown tables. On the 10 worst documents it raised a word-order score (share of word pairs found
in clean papers) from 0.64-0.70 to 0.66-0.80 (clean papers: about 0.82), and on a table-heavy page the
numbers matched the PDF cell for cell. It needs a GPU stack that is not in `requirements.txt`
(`torch` with Apple MPS or CUDA, `transformers>=5`, `pypdfium2`), so run it natively in its own
environment, not in Docker; the 0.8B/4B LightOnOCR variants are impractical on a Mac (no fast
kernels), use the 1B. It works in two phases: `python src/ocr_vlm.py` writes staged text and a per-page
cache to `data/intermediate/ocr_vlm/` (resumable, about 40 s per page on an M4 Pro) and never touches
`data/final`; `python src/ocr_vlm.py --apply` then replaces each document's text and records
`ocr_engine` and `ocr_truncated_pages` in the manifest. Download the model with
`HF_HUB_DISABLE_XET=1` if the default download stalls.

## Step 9: Extract figures and tables

`extract_figs_tbls.py` uses PDFFigures2 to extract captioned figures and tables, including
many vector graphics. They are stored beside each document under `figures/` and `tables/`.

## Step 10: Extract participation counts

`extract_counts.py` searches the beginning of each overview for statements such as:

```text
20 participating teams
received submissions from 15 teams
42 runs were submitted
```

It ignores registration counts and limits such as “98 teams registered” and “each team
could submit up to 5 runs.” It calculates:

```text
coverage_ratio = participant papers / participating teams
```

If no trustworthy number is found, the value is `null`.

## Step 11: Extract code and TIRA links

`find_code.py` scans participant Markdown for GitHub, GitLab, Hugging Face, Zenodo, and
TIRA links. It ignores the bibliography and separates:

- `code_urls`: likely links to the team's own artifacts
- `third_party_urls`: libraries or models used by the team
- `tira_refs`: TIRA URLs or container references

Intermediate results are stored in:

```text
data/intermediate/code/{task_id}.json
```

Every link is reduced to the repository it names (`https://github.com/owner/repo`: no `www`, `.git`
or `/tree/...` path), so one repository is stored once. Profile-only, documentation, and truncated
links are dropped; for Markdown hyperlinks the href is used rather than the line-wrapped visible
text. Each distinct URL is checked once (HEAD, then GET, with retries on rate limits). Dead links
remain as historical evidence with their status (`200` live, `404` gone, `401` gated or missing on
Hugging Face). `--reuse-statuses <old code dir>` reuses earlier 200/404 results after an
extraction change.

**Authors.** Where the source lists no authors (mostly NTCIR and TREC), they were read from the
paper's first page and stored in `data/intermediate/authors_extracted.json`
(`{"task_id|pdf_url": [names]}`). The extraction was done by a language model; each name was then
checked against the page text before it was kept. `authors_source` on every document says
`source_metadata` or `extracted_from_text`. 17 documents have no authors because the page shows none. Lists found wrong by a full audit were
replaced with the names printed on the page (`authors_source` = `corrected_from_text`, from
`data/intermediate/authors_corrections.json`). Author lists are normalised in
`src/clean_authors.py` (one person per entry, affiliations and scraped markup removed); where a
source kept only the first authors, the names read from the page are appended
(`authors_source` = `source_metadata+extracted_from_text`). Titles lose a trailing page range or
author list that some proceedings pages append.

**Links in every document.** Besides `code_urls`, each overview and participant record has `links`:
every code, dataset, model and TIRA link in the text, `{url, kind, third_party, in_references,
own_code_score}` (`src/paper_links.py`). `kind` comes from the host (`huggingface.co/datasets/` and
Kaggle/Figshare/OSF are datasets, other Hugging Face repositories are models, Zenodo is a dataset
when the surrounding text talks about data, else code). Links are not fetched. A link after the
reference list is kept and flagged `in_references`, because teams often put their own repository on
the last page. A document with at least one link also has a `links.json` beside `paper.pdf` and `paper.txt.md`, and
`data/final/paper_links.jsonl` has the same links one per row with `task_id`,
`document` (`overview` or `participant`) and `pdf_url`. Datasets on other sites (project pages,
Google Drive) are not recognised.

**Own-code score.** A link in a paper is not always the team's own code: it may be a library, a
pretrained model, or the organizers' data. Each link therefore gets `own_code_score` (0 to 1) and
`likely_own_code` (score >= 0.7) from a small logistic model over transparent features: task, year
and venue words in the repository name; the repository owner matching a paper author (positive) or
an overview author (negative); "our code is available" versus "based on / pre-trained" wording around
the link; and whether the repository README mentions the task, year or paper title (READMEs are
cached in `data/intermediate/readmes/`). The weights, fitted on 170 hand-labelled links, are in
`find_code.py`. Cross-validated and re-weighted to the real mix of links, the estimate is about 91%
precision and 86% recall; the older `availability_evidence` flag alone had about 91% precision but
only about 38% recall. The labelled sample is small, so treat these as estimates. The CSV column
`code_urls_likely_own` lists the live links with `likely_own_code`.

## Step 12: Build the final corpus

`build_corpus.py` combines the metadata and extracted files into:

```text
data/final/
├── shared_tasks.jsonl
├── shared_tasks.csv
├── shared_tasks_summary.csv   # name, source, year, notebook papers, source links
├── manifest.jsonl
├── report.md
└── {task_id}/
    ├── metadata.json
    ├── overview/
    │   ├── overview.pdf
    │   ├── overview.txt.md
    │   ├── figures/
    │   └── tables/
    └── papers/{paper_id}/
        ├── paper.pdf
        ├── paper.txt.md
        ├── figures/
        └── tables/
```

Before writing, it checks that task IDs and PDF assignments are unique, every task has an
overview and participants, expected files exist, and coverage ratios are plausible.

## What “high confidence” means

High confidence is not a model score and is not based on `coverage_ratio`. It means the
official source gives enough evidence to assign papers without guessing. Normally this
requires:

- one clearly identified organizer overview
- an official task or track grouping
- unambiguous participants
- at least two participants (CLEF requires at least one)
- valid, unique PDF URLs
- no participant PDF assigned to several tasks
- no unresolved paper roles

Source-specific differences:

- **CLEF:** one explicit overview in a CEUR section. Multiple-overview sections remain
  medium confidence.
- **SemEval:** explicit year/task number, one organizer, and at least two clearly marked
  participants.
- **ACL Anthology (non-SemEval):** the curated overview is on the volume page, at least two
  participants are selected by the task's rule, and every PDF link comes from the page.
  `provenance.task_assignment_method` records the evidence: `dedicated_volume` (the whole
  volume is the task's proceedings), `curated_range` (a hand-checked run of papers), or
  `title_marker` (titles name the task, e.g. `Task 2`). Anthology pages have no task
  sections, so tasks whose participants cannot be separated without guessing (SENSEVAL
  per-language tasks, WMT findings, SMM4H, most SIGMORPHON tasks, BioNLP 2011 sub-tasks)
  are not configured. Add a task by appending to `ACL_TASKS` after reading its volume page.
- **TREC and NTCIR:** one overview and at least two participants in an official section.
- **FIRE:** one overview and at least two unambiguous participants in the official section.
- **MediaEval:** one labelled overview and at least two labelled participant papers.
- **SISAP:** an overview, official task evidence, and at least two papers with explicit
  task and team mappings.

Anything ambiguous stays in `needs_review.jsonl`. The default final build includes only
`confidence: "high"`.

## Run only part of the pipeline

Run one source stage directly when debugging:

```bash
python3 src/fetch_trec.py --year 2025
python3 src/collect_trec.py --year 2025
```

The full runner also accepts filters:

```bash
python3 src/run_pipeline.py --volume 2696
python3 src/run_pipeline.py --semeval-year 2025
python3 src/run_pipeline.py --acl-year 2018
python3 src/run_pipeline.py --trec-year 2025
python3 src/run_pipeline.py --ntcir-edition 18
python3 src/run_pipeline.py --fire-year 2025
python3 src/run_pipeline.py --mediaeval-year 2023
python3 src/run_pipeline.py --sisap-year 2025
python3 src/run_pipeline.py --task-id clef2020-touch-touch-2020-argument-retrieval
```

Important: a source filter limits only that source. The full runner still executes the
other collectors. Run individual scripts when you want only one source.

Include review material only intentionally:

```bash
python3 src/run_pipeline.py --confidence medium
python3 src/run_pipeline.py --confidence all
```

The default is `--confidence high`.

## What each script does

| Script | Purpose |
|---|---|
| `run_pipeline.py` | Runs all stages in order and stops on the first failure |
| `fetch_volumes.py` | Downloads CLEF CEUR and DBLP pages |
| `parse_sections.py` | Parses CLEF pages into sections and papers |
| `group_tasks.py` | Creates CLEF overview/participant groups |
| `fetch_acl.py`, `collect_acl.py` | Fetch and collect the curated non-SemEval ACL Anthology tasks |
| `fetch_*.py` | Downloads pages for one source |
| `collect_*.py` | Parses and screens candidates for one source |
| `merge_candidates.py` | Merges candidates and creates the review queue |
| `download_papers.py` | Downloads, validates, stages, and promotes PDF sets |
| `parse_fulltext.py` | Converts PDFs to Markdown and extracts Liteparse assets |
| `extract_figs_tbls.py` | Extracts captioned figures and tables |
| `extract_counts.py` | Finds team and run counts in overview papers |
| `semeval_legacy_tasks.py` | Assigns untitled 2007–2015 SemEval participant papers to tasks from their first pages |
| `find_code.py` | Finds participant code and TIRA links |
| `paper_links.py` | Lists code, dataset, model and TIRA links of every document (`links`, `paper_links.jsonl`) |
| `build_corpus.py` | Produces and validates final indexes and metadata |

## Logs and restarting

Logs are written under `logs/`. The runner creates:

```text
logs/run_pipeline_YYYYMMDD_HHMMSS.log
```

Every stage can be rerun. To move stale or incomplete final task directories back to
staging without downloading anything:

```bash
python3 src/download_papers.py --reconcile-only
```

## Using the corpus

```python
import json
from pathlib import Path

tasks = [
    json.loads(line)
    for line in Path("data/final/shared_tasks.jsonl").read_text().splitlines()
]

for task in tasks:
    target_overview = Path(task["overview"]["fulltext_path"]).read_text()
    participant_inputs = [
        Path(paper["fulltext_path"]).read_text()
        for paper in task["participants"]
    ]
```

During evaluation, do not give `overview.txt.md` to the system. It is the target answer
and would leak the result.

## Current documented corpus

The latest complete run documented here contains:

- 585 tasks
- 6,540 participant papers
- 7,125 documents including overviews
- 99 CLEF, 159 SemEval, 42 TREC, 101 NTCIR, 68 FIRE, 62 MediaEval, 52 other ACL Anthology, and 4 SISAP tasks

These numbers can change when sources or configurations are updated. Thirty-five documents
in that run were marked for optional OCR. Five others had a PDFFigures2-specific failure
while retaining their PDF, Markdown, and Liteparse assets.

## Non-paper filtering and `dropped_documents.jsonl`

`build_corpus.py` drops documents that are not papers: one-page abstracts, under 3,000 characters
of text, poster/slide/sample/topic-list/invited-talk files. A task whose overview is dropped is
removed; any task with fewer than two real participant papers is removed. Each decision is
appended to `data/final/dropped_documents.jsonl` so rebuilds stay repeatable after the files are
deleted. To restore a document, delete its line there and re-run the download stage.

## Research field label (`field`)

Every task carries `field`: `NLP` (language understanding/generation), `IR` (retrieval, search,
ranking, recommendation) or `Other` (neither, e.g. vision, audio, clinical prediction). TREC and
SISAP are IR; SemEval, CoNLL and the ACL workshops are NLP; CLEF, NTCIR, FIRE and MediaEval mix
fields, so their tasks are labelled by the ordered rules in `src/task_field.py` from the task's
subject, not the venue's name. The label is a judgement: borderline tasks (e.g. eRisk, Lifelog,
FIRE's IRSE) follow the rule that is documented in that file.
