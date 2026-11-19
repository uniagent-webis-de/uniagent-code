"""Curated ACL Anthology shared tasks that are not SemEval.

ACL Anthology volumes carry no task sections, so each task is curated by hand from
the volume page: the organizer overview paper plus a rule that selects its
participant papers.  Three kinds of evidence are used and recorded in
``provenance.task_assignment_method``:

``dedicated_volume``  the whole volume is the task's proceedings (CoNLL shared-task
                      volumes); every paper except the overview is a participant.
``curated_range``     participants are the papers between ``first`` and ``last``
                      (inclusive, in volume order), checked by hand.
``title_marker``      participants are the papers in the range whose title matches
                      ``match`` (e.g. ``Task 2`` or a task acronym).

The seed list is the overview papers in ``data/raw/martin_22_shared_tasks.json``
(Martin et al., 2022).  Overviews that cannot be paired with participants without
guessing (SENSEVAL per-language tasks, WMT findings, SMM4H, SIGMORPHON, BioNLP 2011
sub-tasks, ...) are deliberately left out rather than guessed.
"""

from __future__ import annotations


def _task(family: str, year: int, volume: str, overview: str, name: str, **rule) -> dict:
    """One curated task; ``rule`` is any of first, last, match, exclude."""
    return {
        "venue": family,
        "parent_venue": family,
        "year": year,
        "collection_id": volume,
        "overview_id": overview,
        "task_name": name,
        "provider": "acl_anthology",
        "first": rule.get("first"),
        "last": rule.get("last"),
        "match": rule.get("match"),
        "exclude": list(rule.get("exclude", ())),
    }


def _ijcnlp(number: int, overview: str, name: str) -> dict:
    return _task("IJCNLP", 2017, "I17-4", overview, name, match=rf"\bTask[ -]?{number}\b")


ACL_TASKS = [
    # --- CoNLL shared tasks: papers sit inside the main-conference volume ---
    _task("CoNLL", 2000, "W00-07", "W00-0726", "Chunking", first="W00-0727", last="W00-0737"),
    _task("CoNLL", 2003, "W03-04", "W03-0419", "Language-Independent Named Entity Recognition",
          first="W03-0420", last="W03-0435"),
    _task("CoNLL", 2004, "W04-24", "W04-2412", "Semantic Role Labeling", first="W04-2413", last="W04-2422"),
    _task("CoNLL", 2005, "W05-06", "W05-0620", "Semantic Role Labeling", first="W05-0621", last="W05-0639"),
    _task("CoNLL", 2008, "W08-21", "W08-2121", "Joint Parsing of Syntactic and Semantic Dependencies",
          first="W08-2122", last="W08-2140"),
    # --- CoNLL shared tasks with a dedicated proceedings volume ---
    _task("CoNLL", 2009, "W09-12", "W09-1201", "Syntactic and Semantic Dependencies in Multiple Languages"),
    _task("CoNLL", 2010, "W10-30", "W10-3001", "Learning to Detect Hedges and their Scope"),
    _task("CoNLL", 2011, "W11-19", "W11-1901", "Modeling Unrestricted Coreference in OntoNotes"),
    _task("CoNLL", 2012, "W12-45", "W12-4501", "Modeling Multilingual Unrestricted Coreference in OntoNotes"),
    _task("CoNLL", 2013, "W13-36", "W13-3601", "Grammatical Error Correction"),
    _task("CoNLL", 2014, "W14-17", "W14-1701", "Grammatical Error Correction"),
    _task("CoNLL", 2015, "K15-2", "K15-2001", "Shallow Discourse Parsing"),
    _task("CoNLL", 2016, "K16-2", "K16-2001", "Multilingual Shallow Discourse Parsing"),
    _task("CoNLL", 2017, "K17-3", "K17-3001", "Multilingual Parsing from Raw Text to Universal Dependencies"),
    _task("CoNLL", 2018, "K18-2", "K18-2001", "Multilingual Parsing from Raw Text to Universal Dependencies",
          exclude=["K18-2002"]),  # K18-2002 is the separate EPE shared-task overview
    _task("CoNLL", 2018, "K18-3", "K18-3001", "CoNLL-SIGMORPHON Universal Morphological Reinflection"),
    _task("CoNLL", 2019, "K19-2", "K19-2001", "Cross-Framework Meaning Representation Parsing"),
    _task("CoNLL", 2020, "2020.conll-shared", "2020.conll-shared.1",
          "Cross-Framework and Cross-Lingual Meaning Representation Parsing"),
    # --- IJCNLP 2017 shared-task volume: titles name the task number ---
    _ijcnlp(1, "I17-4001", "Chinese Grammatical Error Diagnosis"),
    _ijcnlp(2, "I17-4002", "Dimensional Sentiment Analysis for Chinese Phrases"),
    _ijcnlp(3, "I17-4003", "Review Opinion Diversification"),
    _ijcnlp(4, "I17-4004", "Customer Feedback Analysis"),
    _ijcnlp(5, "I17-4005", "Multi-choice Question Answering in Examinations"),
    # --- *SEM ---
    _task("StarSEM", 2012, "S12-1", "S12-1035", "Resolving the Scope and Focus of Negation",
          first="S12-1036", last="S12-1045"),
    # --- Workshop shared tasks whose system papers follow the overview ---
    _task("NLPTEA", 2018, "W18-37", "W18-3706", "Chinese Grammatical Error Diagnosis",
          first="W18-3707", last="W18-3710"),
    _task("NLPTEA", 2020, "2020.nlptea-1", "2020.nlptea-1.4", "Chinese Grammatical Error Diagnosis",
          first="2020.nlptea-1.5", last="2020.nlptea-1.15"),
    _task("CALCS", 2018, "W18-32", "W18-3219", "Named Entity Recognition on Code-Switched Data",
          first="W18-3220", last="W18-3221"),
    _task("NEWS", 2018, "W18-24", "W18-2409", "Named Entity Transliteration", first="W18-2410", last="W18-2414"),
    _task("MSR", 2018, "W18-36", "W18-3601", "Multilingual Surface Realisation", first="W18-3602", last="W18-3609"),
    _task("WASSA", 2018, "W18-62", "W18-6206", "Implicit Emotions", first="W18-6207", last="W18-6209"),
    _task("CLPsych", 2018, "W18-06", "W18-0604", "Predicting Psychological Health from Childhood Essays",
          first="W18-0605", last="W18-0611", match=r"CLPsych|Childhood Essays|Psychological Health"),
    _task("BEA", 2018, "W18-05", "W18-0507", "Complex Word Identification",
          first="W18-0509", match=r"Complex Word|CWI"),
    _task("PharmaCoNER", 2019, "D19-57", "D19-5701", "Pharmacological Substances, Compounds and Proteins NER",
          first="D19-5702", last="D19-5717", match=r"PharmaCoNER|Pharmaco"),
    _task("TextGraphs", 2019, "D19-53", "D19-5309", "Multi-Hop Inference for Explanation Regeneration",
          first="D19-5310", match=r"TextGraphs|Explanation|Multi-Hop"),
    _task("COIN", 2019, "D19-60", "D19-6007", "Commonsense Inference in Natural Language Processing",
          first="D19-6008", last="D19-6012"),  # D19-6013 is a regular workshop paper
    _task("MADAR", 2019, "W19-46", "W19-4622", "Arabic Fine-Grained Dialect Identification",
          first="W19-4623", last="W19-4639"),
    _task("LoResMT", 2020, "2020.loresmt-1", "2020.loresmt-1.4", "Zero-Shot for Low-Resource Languages",
          first="2020.loresmt-1.5", last="2020.loresmt-1.8"),
    _task("AmericasNLP", 2021, "2021.americasnlp-1", "2021.americasnlp-1.23",
          "Open Machine Translation for Indigenous Languages of the Americas",
          first="2021.americasnlp-1.24", last="2021.americasnlp-1.30"),
    _task("CLPsych", 2019, "W19-30", "W19-3003", "Predicting the Degree of Suicide Risk in Reddit Posts",
          first="W19-3004", last="W19-3005"),
    _task("GAP", 2019, "W19-38", "W19-3801", "Gendered Ambiguous Pronouns", first="W19-3811", last="W19-3816"),
    _task("WNUT", 2020, "2020.wnut-1", "2020.wnut-1.33", "Extracting Entities and Relations from Wet Lab Protocols",
          first="2020.wnut-1.34", last="2020.wnut-1.40"),
    _task("WNUT", 2020, "2020.wnut-1", "2020.wnut-1.41", "Identification of Informative COVID-19 English Tweets",
          first="2020.wnut-1.42", last="2020.wnut-1.80", match=r"Task[ -]?2\b"),
    _task("SIGTYP", 2020, "2020.sigtyp-1", "2020.sigtyp-1.1", "Prediction of Typological Features",
          first="2020.sigtyp-1.2", last="2020.sigtyp-1.6"),
    _task("CASE", 2021, "2021.case-1", "2021.case-1.23", "Fine-Grained Event Classification in News-Like Text Snippets",
          first="2021.case-1.24", last="2021.case-1.26"),
    _task("CMCL", 2021, "2021.cmcl-1", "2021.cmcl-1.7", "Eye-Tracking Prediction",
          first="2021.cmcl-1.8", last="2021.cmcl-1.17"),
    _task("MEDIQA", 2021, "2021.bionlp-1", "2021.bionlp-1.8", "Summarization in the Medical Domain",
          first="2021.bionlp-1.9", last="2021.bionlp-1.12"),
    _task("NADI", 2021, "2021.wanlp-1", "2021.wanlp-1.28", "Nuanced Arabic Dialect Identification",
          first="2021.wanlp-1.29", last="2021.wanlp-1.35"),
    _task("WANLP", 2021, "2021.wanlp-1", "2021.wanlp-1.36", "Sarcasm and Sentiment Detection in Arabic",
          first="2021.wanlp-1.37", last="2021.wanlp-1.53"),
    _task("SIGMORPHON", 2021, "2021.sigmorphon-1", "2021.sigmorphon-1.13", "Multilingual Grapheme-to-Phoneme Conversion",
          first="2021.sigmorphon-1.14", last="2021.sigmorphon-1.17"),
    _task("TextGraphs", 2021, "2021.textgraphs-1", "2021.textgraphs-1.17", "Multi-Hop Inference for Explanation Regeneration",
          first="2021.textgraphs-1.18", last="2021.textgraphs-1.20"),
    _task("WASSA", 2021, "2021.wassa-1", "2021.wassa-1.10", "Predicting Empathy and Emotion in Reaction to News Stories",
          first="2021.wassa-1.11", last="2021.wassa-1.12"),
    _task("LT-EDI", 2021, "2021.ltedi-1", "2021.ltedi-1.8", "Hope Speech Detection for Equality, Diversity and Inclusion",
          first="2021.ltedi-1.9", match=r"LT-EDI|Hope"),
]


def selected_tasks(year: int | None = None) -> list[dict]:
    """Return curated tasks, optionally restricted to one year."""
    if year is None:
        return list(ACL_TASKS)
    return [task for task in ACL_TASKS if task["year"] == year]


def volume_url(collection_id: str) -> str:
    """Return the ACL Anthology proceedings-page URL of a volume."""
    return f"https://aclanthology.org/volumes/{collection_id}/"


def selected_volumes(year: int | None = None) -> list[str]:
    """Return the distinct volume ids needed by the selected tasks."""
    return sorted({task["collection_id"] for task in selected_tasks(year)})
