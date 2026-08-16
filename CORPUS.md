# Shared-Task Corpus — Build, Layout, and Usage

A corpus of CLEF shared tasks where each entry links one **overview paper** (written by the
lab organizers, summarising the whole task) to the **notebook papers** written by the teams
that participated in it.

The intended use is generation: the notebook papers are the inputs, the overview paper is
the target output.

**42 tasks · 444 notebook papers · 486 parsed documents · CLEF 2018–2025 · 22 labs**

---

## 1. Where the data comes from

Everything derives from two public sources, both fetched once and cached:

| Source | Role |
|---|---|
| [CEUR-WS](https://ceur-ws.org) volume index pages | Authoritative table of contents: which papers exist, in which lab section, in what order |
| [DBLP](https://dblp.org) working-notes records | Cross-check only — confirms titles and supplies cleaner author name spellings |

Eight volumes, one per CLEF edition: 2125 (2018), 2380, 2696, 2936, 3180, 3497, 3740,
4038 (2025).

DBLP never adds or removes a paper. CEUR-WS is authoritative for *which* papers exist and
what section they sit in; DBLP only corrects author spellings where the normalized titles
match (99%+ of papers).

**Every `pdf_url` in the corpus was read from an `href` on a CEUR-WS index page.** None are
constructed from a filename pattern — the patterns are not stable across volumes
(`paper-199.pdf` in Vol-3497, `paper_281.pdf` in Vol-4038), so guessing them silently
produces dead links.

---

## 2. How tasks were identified

This is the part worth understanding before you trust an entry, because it is where the
judgement lives.

A CEUR volume is organised into lab sections (PAN, Touché, eRisk, …). Within a section we
need to know which overview paper each notebook paper belongs to. Two cases:

**One overview in the section** → every other paper in that section is its participant.
This is structural, derived from the published table of contents, and is the only case
included in the released corpus. Marked `confidence: "high"`,
`task_assignment_method: "section_grouping"`.

**Several overviews in the section** → assignment falls back to matching notebook titles
against overview titles. This is *not* reliable, so those entries are marked
`confidence: "medium"` and written to `data/intermediate/needs_review.jsonl` for human
review. **156 of 198 candidate tasks are in this state and are excluded from the released
corpus.**

> The original plan assumed overviews and their participants appear contiguously, so
> positional grouping would work throughout. They do not: CEUR volumes list *all* of a
> lab's overviews first, then the notebook papers, in an order that is neither per-task
> nor alphabetical. That is why multi-overview sections need review rather than trust.

### Two failure modes that were found and fixed

Both were caught by reading the data rather than by tests passing, and both are worth
knowing about if you extend this to other venues:

- **Organizer papers that never say "Overview".** The ELOQUENT 2024 section publishes three
  organizer task papers, but only one has "Overview" in its title. The other two
  (`ELOQUENT 2024 — Topical Quiz Task`, `— Robustness Task`) were initially filed as
  participant submissions. Detection now also matches the lab-branded
  `<Lab> <Year> — <Name> Task` shape.
- **A hidden second task.** CLEF eHealth 2021 has two real overviews, but the second is
  titled `Consumer Health Search at CLEF eHealth 2021` — invisible to any keyword rule.
  The section looked single-overview and was wrongly trusted. Now, if the detected overview
  names its own task number and a "participant" names a *different* one, the task is
  downgraded to review rather than trusted.

An author-overlap rule was tried for both and **rejected**: lab organizers routinely also
submit competing systems (`DPRL Systems in the CLEF 2021 ARQMath Lab`, `Organiser Team at
ImageCLEFlifelog 2020`), so it flagged ~48 genuine participant papers.

---

## 3. Files and layout

```
data/final/
├── shared_tasks.jsonl      one JSON record per task — the primary artifact
├── shared_tasks.csv        the same, flattened one row per task, for spreadsheets
├── report.md               generated summary: counts, coverage, link stats
└── fulltext/
    ├── README.md
    ├── manifest.jsonl      one record per parsed document
    └── {task_id}/
        ├── overview.md                          the target output
        ├── participants/{paper_stem}.md         the inputs
        ├── figures/{doc}/img_p4_1.png           figures, per document
        └── tables/{doc}/
            ├── table-01.md                      table as parsed text
            └── page011-table01.png              table cropped from the page
```

`{doc}` is `overview` or a notebook paper's stem. `{paper_stem}` matches the source PDF
filename on CEUR-WS, so any document traces back to its origin.

The raw PDFs are **not** in git — they are re-fetchable (see §7) and were removed to keep
the repository usable.

### Task record

```json
{
  "task_id": "clef2020-touch-touch-2020-argument-retrieval",
  "venue": "Touché", "parent_venue": "CLEF", "year": 2020,
  "task_name": "Touché 2020: Argument Retrieval",
  "ceur_volume": "2696",
  "overview": {
    "title": "Overview of Touché 2020: Argument Retrieval",
    "pdf_url": "https://ceur-ws.org/Vol-2696/paper_261.pdf",
    "authors": ["Alexander Bondarenko", "..."],
    "is_umbrella": false,
    "fulltext_path": "data/final/fulltext/clef2020-.../overview.md",
    "figures_dir": "...", "n_figures": 0,
    "tables_dir": "...",  "n_tables": 6
  },
  "participants": [
    {
      "title": "An Open-Domain Web Search Engine for Answering Comparative Questions",
      "authors": ["..."],
      "pdf_url": "https://ceur-ws.org/Vol-2696/paper_130.pdf",
      "team_name": null,
      "fulltext_path": "data/final/fulltext/clef2020-.../participants/paper_130.md",
      "code_urls": ["https://github.com/hemiipatu/Blocklists.git"],
      "code_url_details": [{"url": "...", "status": "200", "availability_evidence": false}],
      "third_party_urls": ["https://github.com/huggingface/transformers"],
      "tira_refs": [], "n_figures": 1, "n_tables": 1
    }
  ],
  "counts": {
    "notebook_papers": 10,
    "teams_claimed_in_overview": 17,
    "runs_claimed_in_overview": 41,
    "coverage_ratio": 0.588
  },
  "provenance": {
    "task_assignment_method": "section_grouping",
    "confidence": "high",
    "extracted_at": "2026-08-16"
  }
}
```

In the CSV, `participant_pdf_urls` and `participant_fulltext_paths` are joined by `; ` in
the **same order**, so the columns align positionally.

---

## 4. Field notes

**`coverage_ratio`** = `notebook_papers / teams_claimed_in_overview`. Not every team that
competes writes a paper, so a ratio below 1 is normal and expected, not a bug — Touché 2020
reports 17 teams and 41 runs but published 10 notebook papers. **It is `null` for 21 of 42
tasks**, where the overview does not state a participation count in extractable prose. Team
counts are only taken from statements about *actual participation*; registration counts
("98 teams registered") are deliberately refused, since they would inflate the ratio.

**`code_urls`** contains links plausibly pointing at the *team's own* code. Dependencies the
team merely used are excluded into `third_party_urls`. This distinction matters: before it
existed, ~48% of stored links were things like `huggingface/transformers`, `nltk`, and
`meta-llama` presented as team submissions. Links are never dropped for being dead — a dead
repository is still evidence the team published code — so filter on
`code_url_details[].status` yourself. `availability_evidence: true` marks links that
appeared beside an explicit code-release statement.

**`is_umbrella`** is `true` when one overview serves several sub-tasks. Best-effort: a lab
whose titles omit task numbers entirely reads as non-umbrella even if it ran several.

**`team_name`** is extracted only from the two attribution shapes CEUR titles actually use
(`TEAM at Venue Year: …`, `TEAM@Venue: …`), and is `null` rather than guessed otherwise —
so expect it on roughly half of participants (205/444).

---

## 5. Full text, figures, and tables

Text comes from each PDF's own text layer via [liteparse](https://github.com/run-llama/liteparse),
output as Markdown to preserve heading structure. 18.4M characters across 486 documents.

**OCR is not used, and does not need to be.** Measured across all 504 PDFs: 0 are garbled,
0 are scanned page images, and exactly **1** lacks a usable text layer
(`Vol-3740/paper-124.pdf`, whose text is drawn as vector outlines). It is flagged
`needs_ocr` in `manifest.jsonl`. If you want it, liteparse delegates OCR over HTTP, so serve
a model and point at it:

```bash
./src/parse_fulltext.py --ocr-server-url http://localhost:8080 --only-needs-ocr
```

**Figures** (1,291) are the raster images embedded in the PDFs, referenced inline from the
markdown so a document still reads as a whole. Figures drawn as *vector* graphics — many
plots and diagrams — are not files and are not extracted; their captions remain in the text.

**Tables** exist in two independent views, and this distinction matters:

| View | Count | How it is produced |
|---|---|---|
| `table-NN.md` | 3,199 | The parser's text reconstruction, in document order |
| `pageNNN-tableNN.png` | 3,055 | Cropped from the page using the paper's own ruling lines |

**They are not index-matched, and where they disagree, trust the image.** The text
reconstruction is unreliable for large tables — in the eRisk 2018 overview the parser
collapsed a 34-team results table into a single markdown row. Pairing images to markdown
tables by matching cell text was tried and produced images filed under the wrong table, so
images are now named for the page they came from and always show what they claim to.

---

## 6. Using it

```python
import json
from pathlib import Path

tasks = [json.loads(l) for l in open("data/final/shared_tasks.jsonl")]

for task in tasks:
    target = Path(task["overview"]["fulltext_path"]).read_text()
    inputs = [Path(p["fulltext_path"]).read_text() for p in task["participants"]]
    # inputs -> target
```

Filter to the best-evidenced entries:

```python
solid = [t for t in tasks
         if t["counts"]["coverage_ratio"] and t["counts"]["coverage_ratio"] >= 0.7
         and not t["overview"]["is_umbrella"]]
```

> **Before you build a test split:** the overview papers are the target output, and their
> full text ships inside this corpus. Any blind evaluation split must withhold
> `overview.md`, or the answer leaks.

---

## 7. Reproducing

Requires `pyenv activate uniagent`, plus `lit` (`npm i -g @llamaindex/liteparse`). Every
stage is independently re-runnable and caches to disk; nothing re-fetches what is already
there. Run from the project root:

```bash
./src/fetch_volumes.py     # CEUR + DBLP pages     -> data/raw/
./src/parse_sections.py    # sections and papers   -> data/intermediate/sections/
./src/group_tasks.py       # tasks                 -> data/intermediate/all_candidates.jsonl
./src/extract_counts.py    # claimed team/run counts
./src/find_code.py         # code + TIRA links     (slow: fetches every PDF)
./src/parse_fulltext.py    # markdown, figures, tables
./src/build_corpus.py      # assemble data/final/
```

`build_corpus.py` validates before writing anything, and refuses to emit the corpus if a
check fails: every task has exactly one overview and ≥1 participant, no duplicate `task_id`
or `pdf_url`, and every `coverage_ratio` is null or within `[0, 1.5]`.

`pytest` covers the parsing and grouping logic against saved fixtures — 68 tests, no
network.

---

## 8. Known limitations

1. **42 of 198 candidate tasks are released.** The other 156 need human review of their
   overview→participant assignment (§2) and sit in `data/intermediate/needs_review.jsonl`.
2. **`coverage_ratio` is unknown for half the corpus** (21/42), so the plan's intended
   quality filter cannot be applied everywhere.
3. **Vector figures are not extracted** — only raster images are, which is why 267 of 486
   documents have figure files rather than nearly all.
4. **Markdown tables are unreliable for large tables.** Use the images.
5. **CLEF only.** SemEval, standalone PAN, and Touché editions outside CLEF are not
   included; the target of 30–50 tasks was met without them.
6. **One document lacks a usable text layer** and needs OCR to be complete (§5).
