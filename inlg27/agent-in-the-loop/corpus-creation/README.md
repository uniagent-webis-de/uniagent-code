# Local corpus builder

Generated data is kept locally under `data/` and can be uploaded to Ceph manually after
verification. The pipeline never uploads data automatically.

# Shared-Task Corpus — Build, Layout, and Usage

A corpus of shared tasks where each entry links one **overview paper** (written by the
organizers, summarising the whole task) to the **notebook papers** written by the teams
that participated in it. The current corpus covers CLEF, FIRE, MediaEval, NTCIR, SemEval,
and TREC, with more high-precision source-specific collectors planned for other ACL/IR
venues.

The intended use is generation: the notebook papers are the inputs, the overview paper is
the target output.

The generated counts are recorded in `data/final/report.md`; the default pipeline emits all
high-confidence candidates that pass screening.

---

## 1. Where the data comes from

The corpus draws on public sources that are fetched once and cached. Source-specific
collectors use the same candidate contract and are merged before the paper-download stages:

| Source | Role |
|---|---|
| [CEUR-WS](https://ceur-ws.org) volume index pages | Authoritative table of contents: which papers exist, in which lab section, in what order |
| [DBLP](https://dblp.org) working-notes records | Cross-check only — confirms titles and supplies cleaner author name spellings |
| [ACL Anthology](https://aclanthology.org) proceedings pages | Official SemEval collection pages, paper metadata, and source-provided PDF links |
| [NIST TREC proceedings](https://trec.nist.gov/proceedings/proceedings.html) | Authoritative TREC track sections, overview papers, participant papers, and official PDF links |
| [DBLP TREC records](https://dblp.org/db/conf/trec/index.html) and [TIRA](https://www.tira.io/tasks) | Supplemental TREC cross-checks; neither source creates a paper or task grouping |
| [NII NTCIR proceedings](https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings/index.html) | Authoritative NTCIR proceedings pages, task sections, overview papers, participant papers, and official PDF links |
| [DBLP NTCIR records](https://dblp.org/db/conf/ntcir/index.html) and [TIRA](https://www.tira.io/tasks) | Supplemental NTCIR cross-checks; neither source creates a paper or task grouping |
| [FIRE official archive](https://fire.irsi.org.in/fire/2025/home) and [CEUR FIRE volumes](https://ceur-ws.org/Vol-4173/) | Authoritative FIRE edition/track pages and working-notes sections, overview papers, participant papers, and official PDF links |
| [DBLP FIRE records](https://dblp.org/db/conf/fire/index.html) and [TIRA](https://www.tira.io/tasks) | Supplemental FIRE cross-checks; neither source creates a paper or task grouping |
| [MediaEval official history and edition pages](https://multimediaeval.github.io/about/) and [CEUR MediaEval proceedings](https://ceur-ws.org/Vol-3658/) | Authoritative MediaEval task sections, explicit overview/working-notes/quest-for-insight roles, and official PDF links |
| [DBLP MediaEval records](https://dblp.org/db/conf/mediaeval/index.html) and [TIRA](https://www.tira.io/tasks) | Supplemental MediaEval cross-checks; neither source creates a paper or task grouping |

Twenty-six volumes, one per CLEF Working Notes edition from 2000 through 2025: volumes
1166–1179 (2000–2013), 1180 (2014), 1391 (2015), 1609 (2016), 1866 (2017), and
2125–4038 (2018–2025).

DBLP never adds or removes a paper. CEUR-WS is authoritative for *which* papers exist and
what section they sit in; DBLP only corrects author spellings where the normalized titles
match. In the latest all-years run, DBLP served anti-bot challenge pages, so no DBLP
matches contributed to the corpus and CEUR author metadata was retained.

**Every `pdf_url` in the corpus was read from an `href` on the authoritative source page
for its venue.** None are constructed from a filename pattern — the patterns are not
stable across collections. One NTCIR-12 IMine-2 href is preserved as
`source_url_original` because the official ToC uses a stale `SongX` filename while the
served PDF is `SongM`; the correction is explicit and source-specific.

---

## 2. How tasks were identified

Each source has its own conservative collector. Collectors write source-specific records to
`data/intermediate/candidates/*.jsonl`; `merge_candidates.py` validates the common schema,
demotes collisions or malformed records, and combines the candidates. High-confidence
records are eligible for the final corpus automatically. Medium-confidence candidates and
unresolved source records are combined in `data/intermediate/needs_review.jsonl`, including
the existing CLEF review candidates.

The first non-CLEF collector targets all SemEval editions represented by the ACL Anthology
venue index (2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015,
2014, 2013, 2012, 2010, and 2007). It requires an explicit `SemEval-YYYY Task N`
marker, one organizer paper, at least two participant papers, official PDF links, and
unique document URLs before a task is marked high confidence. The parser accepts both
`Team at SemEval-YYYY` and the frequent compact `TeamatSemEval-YYYY` title form. For
legacy ACL volumes, an exact task-number reference is also accepted for participant
papers because those titles often omit the `at SemEval` phrase. Other title forms remain
review material. The SENSEVAL predecessor editions are intentionally excluded.

The TREC collector scans every completed NIST edition from 1992 through 2025. It uses
the official NIST track section as the authoritative grouping, supports both modern and
legacy proceedings HTML, and attaches separately listed overview papers when their track
name matches exactly. A task is high confidence only when it has exactly one overview,
at least two unambiguous participant papers, official PDF links, unique PDFs, and no
participant listed under multiple tracks. DBLP and TIRA are retained as supplemental
provenance only. Missing required PDFs automatically demote the affected task to the
existing review queue; they do not stop the rest of the corpus from being built.

The NTCIR collector scans the completed NII proceedings for NTCIR-1 through NTCIR-18
(1999–2025), supporting modern sectioned ToCs and the older flat and numbered layouts.
The official NII task section is authoritative; DBLP and TIRA are supplemental
cross-checks only. A task is high confidence only when it has exactly one organizer
overview, at least two unambiguous participant papers, official PDF links, unique PDFs,
and no participant shared across task sections. NTCIR-19 is not included because its
completed proceedings are not available in the configured official collection. Historical
groups without sufficient organizer/participant evidence remain in the review queue.

The FIRE collector scans every edition listed by the official archive (2008 and
2010–2025; the archive has no 2009 edition link). CEUR working-notes volumes provide the
authoritative section structure and PDF links for FIRE 2015–2025; the official FIRE pages,
DBLP, and TIRA are retained as provenance and cross-checks. The older 2008 and 2010–2014
editions are fetched/configured but remain review-only when the public proceedings source
does not expose a complete parseable set of official PDF links. FIRE uses the same
high-confidence rule as the other collectors: exactly one organizer overview, at least
two unambiguous participant papers, official PDFs, unique URLs, and no cross-section
participant collisions. Sections with multiple overview papers, missing overviews, or too
few participants remain in the shared review queue.

The MediaEval collector scans the official history and edition pages for 2010–2023 and
2025–2026; the official history has no 2024 edition. CEUR proceedings provide the
authoritative role-labelled structure for 2011–2023 (volumes 807, 927, 1043, 1263, 1436,
1739, 1984, 2283, 2670, 2882, 3181, 3583, and 3658). A task is high confidence only when
there is exactly one explicit organizer overview, at least two explicitly labelled
participant/working-notes papers, official PDF links, unique URLs, and no participant
shared across track sections. The 2011 organizer overview covering Genre Tagging and Rich
Speech Retrieval is represented as one umbrella task with both role sections. Legacy 2010
pages, editions whose proceedings expose insufficient evidence, and current editions
without parseable official PDF sections remain review-only. DBLP and TIRA are supplemental
cross-checks and never create task groupings.

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
review. In the current all-years CLEF scan, 105 of 384 candidate task groups are high
confidence; the remaining 279 are excluded from the released corpus pending review.

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
├── manifest.jsonl          one record per parsed document
├── report.md               generated summary: counts, coverage, link stats
└── {task_id}/
    ├── metadata.json       the complete task record and provenance
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

`{paper_id}` is derived from the source PDF filename on CEUR-WS, so any document traces
back to its origin through both the directory name and `pdf_url` in the metadata.

The generated `data/` directory and `logs/` are local-only and are not committed to Git.
The raw PDFs remain beside their parsed Markdown so the corpus can be copied as one
self-contained directory.

All paths above are relative to
`/Users/pierreachkar/Documents/projects/uniagent-code/inlg27/agent-in-the-loop/corpus-creation`
when run in the shared workspace. The pipeline does not upload data to Ceph or GitHub.

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
    "pdf_path": "data/final/clef2020-.../overview/overview.pdf",
    "fulltext_path": "data/final/clef2020-.../overview/overview.txt.md",
    "figures_dir": "...", "n_figures": 0,
    "tables_dir": "...",  "n_tables": 6
  },
  "participants": [
    {
      "title": "An Open-Domain Web Search Engine for Answering Comparative Questions",
      "authors": ["..."],
      "pdf_url": "https://ceur-ws.org/Vol-2696/paper_130.pdf",
      "team_name": null,
      "pdf_path": "data/final/clef2020-.../papers/paper_130/paper.pdf",
      "fulltext_path": "data/final/clef2020-.../papers/paper_130/paper.txt.md",
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
reports 17 teams and 41 runs but published 10 notebook papers. **It is `null` for 328 of 501
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

**`team_name`** is extracted only from the source-specific attribution shapes recognized by
the collectors, and is `null` rather than guessed otherwise — it was extracted for 3,418
of 5,880 participants in the current corpus.

---

## 5. Full text, figures, and tables

Text comes from each PDF's own text layer via [liteparse](https://github.com/run-llama/liteparse),
output as Markdown to preserve heading structure. The PDF is parsed once for its text and
Liteparse assets; later count and code-link stages read the generated Markdown. A separate
PDFFigures2 pass detects captioned figures and tables, including many vector-rendered
figures, and stores its outputs beside those assets. The current corpus contains 161.7M
extracted characters across 6,381 documents.

**OCR is opt-in.** Thirty-five of the 6,381 PDFs have a thin or missing text layer and are
flagged `needs_ocr` in `manifest.jsonl`; the other 6,346 were parsed without OCR. If you want to
retry those documents, liteparse delegates OCR over HTTP, so serve a model and point at it:

```bash
./src/parse_fulltext.py --ocr-server-url http://localhost:8080 --only-needs-ocr
```

**Figures** (19,617 in the current corpus) are the raster images embedded in the
PDFs, referenced inline from the markdown so a document still reads as a whole. The
PDFFigures2 pass adds captioned figure renderings, including figures drawn as *vector*
graphics. Its files use the `pdffigures2-` prefix so both extractors' outputs remain
auditable and cannot overwrite each other.

**Tables** in the final corpus are rendered by PDFFigures2:

| View | Count | How it is produced |
|---|---|---|
| `tables/pdffigures2-*.png` | 24,169 | Captioned table renderings from PDFFigures2 |

The parsed Markdown still retains table content inline. The extraction stage removes the
older standalone `table-NN.md` and cropped `pageNNN-tableNN.png` assets so the final
`tables/` directories have one auditable representation.

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
> `overview.txt.md`, or the answer leaks.

---

## 7. Reproducing

Setup — note the parser is an npm package, so `pip install` alone is not enough. The
pipeline also needs Java plus a local PDFFigures2 checkout or assembled JAR:

```bash
pyenv activate uniagent
pip install -r requirements.txt
npm i -g @llamaindex/liteparse   # provides the `lit` command
mkdir -p third_party
git clone https://github.com/allenai/pdffigures2.git third_party/pdffigures2
(cd third_party/pdffigures2 && sbt assembly)
```

If `sbt` is not available, pass an assembled JAR instead:

```bash
./src/run_pipeline.py --pdffigures2-jar /path/to/pdffigures2.jar
```

Every stage is independently re-runnable and caches to disk; nothing re-fetches what is
already there. Run from the project root:

```bash
./src/run_pipeline.py      # run all stages below in order
./src/fetch_volumes.py     # CEUR + DBLP pages     -> data/raw/
./src/parse_sections.py    # sections and papers   -> data/intermediate/sections/
./src/group_tasks.py       # CLEF candidates       -> data/intermediate/candidates/clef.jsonl
./src/fetch_semeval.py     # ACL SemEval pages     -> data/raw/acl_anthology/semeval/
./src/collect_semeval.py   # SemEval candidates    -> data/intermediate/candidates/semeval.jsonl
./src/fetch_trec.py        # NIST TREC pages       -> data/raw/trec/
./src/collect_trec.py      # TREC candidates       -> data/intermediate/candidates/trec.jsonl
./src/fetch_ntcir.py       # NII NTCIR pages       -> data/raw/ntcir/
./src/collect_ntcir.py     # NTCIR candidates      -> data/intermediate/candidates/ntcir.jsonl
./src/fetch_fire.py        # FIRE archive + CEUR   -> data/raw/fire/
./src/collect_fire.py      # FIRE candidates       -> data/intermediate/candidates/fire.jsonl
./src/fetch_mediaeval.py   # MediaEval pages + CEUR -> data/raw/mediaeval/
./src/collect_mediaeval.py # MediaEval candidates   -> data/intermediate/candidates/mediaeval.jsonl
./src/merge_candidates.py  # merged candidates     -> data/intermediate/all_candidates.jsonl
./src/download_papers.py   # PDFs                  -> data/final/{task_id}/
./src/parse_fulltext.py    # Markdown, figures, tables -> data/final/{task_id}/
./src/extract_figs_tbls.py # captioned figures/tables -> document figures/ and tables/
./src/extract_counts.py    # counts from overview Markdown
./src/find_code.py         # code + TIRA links from participant Markdown
./src/build_corpus.py      # indexes, metadata, report -> data/final/
```

The complete local run is:

```bash
./src/run_pipeline.py
```

Use `--fire-year YYYY` or `--mediaeval-year YYYY` when developing or refreshing one source
edition only; without either option, the runner scans all configured editions.

The runner is resumable and writes its combined progress log to
`logs/run_pipeline_YYYYMMDD_HHMMSS.log`. Each individual stage also writes a readable
`filemode="w"` log in `logs/`.

By default, `build_corpus.py` emits all high-confidence candidates selected by the
pipeline. Use `--confidence medium` or `--confidence all` only when you intentionally want
to include review material. Use `--target N` as an optional experimental cap.

`build_corpus.py` validates before writing anything, and refuses to emit the corpus if a
check fails: every task has exactly one overview and ≥1 participant, no duplicate `task_id`
or `pdf_url`, and every `coverage_ratio` is null or within `[0, 1.5]`.

`pytest` covers the parsing, layout, download caching, PDFFigures2 integration, enrichment,
candidate screening, and grouping logic against saved fixtures — with no network access.

---

## 8. Known limitations

1. **The initial screen is conservative.** The current released corpus contains 105
   high-confidence CLEF tasks, 68 FIRE tasks, 62 MediaEval tasks, 102 NTCIR tasks, 122
   SemEval tasks, and 42 TREC tasks: 501 tasks and 5,880 participant papers in total. The
   TREC collector scanned
   all 34 configured editions from 1992–2025; two otherwise high-confidence TREC groups
   were automatically moved to review because 25 required official PDFs were unavailable.
   The NTCIR collector scanned NTCIR-1 through NTCIR-18; historical groups without
   sufficient evidence and NTCIR-19 remain outside the released corpus. FIRE scanned all
   17 configured archive editions, with complete CEUR working-notes structure available for
   2015–2025; older editions remain in review when their public source pages do not expose
   enough official PDF evidence. MediaEval scans 2010–2023 and 2025–2026; legacy and
   insufficiently evidenced editions remain in review. CLEF scans 2000–2025, but the 2000
   volume currently has no high-confidence grouping. The review file contains
   medium-confidence candidates and unresolved records from all six sources. These numbers
   can change as more venues are added or source pages are refreshed.
2. **`coverage_ratio` is source-dependent.** It is unknown where an overview's claimed
   team count cannot be extracted, so the plan's coverage-based ranking is only partially
   available until more source-specific count extractors are added.
3. **PDFFigures2 is a separate external dependency.** The pipeline fails clearly if its
   checkout/JAR or Java/SBT is missing; Liteparse assets remain intact and the run can be
   resumed after setup.
4. **Markdown tables are unreliable for large tables.** Use the images.
5. **Coverage is metadata-first.** The SemEval collector covers the configured ACL
   Anthology editions, the TREC collector covers the configured NIST proceedings editions,
   the NTCIR collector covers NTCIR-1 through NTCIR-18 in the official NII collection, and
   the FIRE collector covers all configured official archive editions while using CEUR for
   its complete 2015–2025 working-notes structure. Ambiguous historical records remain in
   review. Additional source pages can be added as source-specific collectors without
   changing the downstream document pipeline.
6. **Unassigned SemEval papers remain review material.** Papers whose title does not
   explicitly name a task are preserved in the SemEval review file rather than assigned by
   guesswork.
7. **Thirty-five documents have thin or missing text layers** and are flagged for optional
   OCR (§5); five additional documents have a recorded PDFFigures2-specific failure while
   retaining their Liteparse assets.
