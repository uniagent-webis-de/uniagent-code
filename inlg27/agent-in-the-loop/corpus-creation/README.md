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
- SemEval: 2007, 2010, and 2012–2026 where listed by ACL Anthology
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

Links are checked, but dead links remain as historical evidence with their status.

## Step 12: Build the final corpus

`build_corpus.py` combines the metadata and extracted files into:

```text
data/final/
├── shared_tasks.jsonl
├── shared_tasks.csv
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
| `fetch_*.py` | Downloads pages for one source |
| `collect_*.py` | Parses and screens candidates for one source |
| `merge_candidates.py` | Merges candidates and creates the review queue |
| `download_papers.py` | Downloads, validates, stages, and promotes PDF sets |
| `parse_fulltext.py` | Converts PDFs to Markdown and extracts Liteparse assets |
| `extract_figs_tbls.py` | Extracts captioned figures and tables |
| `extract_counts.py` | Finds team and run counts in overview papers |
| `find_code.py` | Finds participant code and TIRA links |
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

- 501 high-confidence tasks
- 5,880 participant papers
- 6,381 documents including overviews
- 105 CLEF, 122 SemEval, 42 TREC, 102 NTCIR, 68 FIRE, and 62 MediaEval tasks
- no released SISAP task yet because available editions did not pass all public-PDF checks

These numbers can change when sources or configurations are updated. Thirty-five documents
in that run were marked for optional OCR. Five others had a PDFFigures2-specific failure
while retaining their PDF, Markdown, and Liteparse assets.
