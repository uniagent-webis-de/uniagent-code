"""Label each shared task with its research field: NLP, IR, or Other.

NLP    language understanding / generation (classification, extraction, QA, MT, parsing...)
IR     retrieval, search, ranking, recommendation, search-engine evaluation
Other  neither (vision, audio, EEG, clinical prediction, privacy, ...)

Venues that sit in one community get a default (TREC and SISAP are IR; SemEval, CoNLL and
the ACL workshops are NLP). CLEF, NTCIR, FIRE and MediaEval mix fields, so their tasks are
labelled by the ordered rules below: the first pattern matching ``"<venue> <task name>"``
wins, which lets a specific rule (e.g. interactive cross-language QA is IR) precede a
broader one (QA is NLP). The label follows the task's actual subject, not the venue's name,
so FIRE's "Information Retrieval in Software Engineering" (code-comment classification) is NLP.
"""

import re

NLP, IR, OTHER = "NLP", "IR", "Other"

VENUE_DEFAULT = {"TREC": IR, "SISAP": IR}

# Task-specific corrections to the venue/keyword rules, checked first. Each was confirmed by
# an independent blind labelling pass (95% agreement) and the task's overview abstract.
EXCEPTIONS: list[tuple[str, str]] = [
    (r"^SemEval .*Fact-Checked Claim Retrieval", IR),   # retrieve fact-checks for a post
    (r"^FIRE .*(\bIRSE\b|Information Retrieval in Software Engineering)", NLP),  # code-comment classification
    (r"^TREC .*Incident Streams", NLP),                  # classify crisis tweets by info type
    (r"^FIRE .*Information Extraction from Microblogs", IR),  # FIRE 2016: retrieve tweets matching needs
]
MIXED_VENUES = {"CLEF", "NTCIR", "FIRE", "MediaEval"}

# Ordered: first match wins. Patterns are matched case-insensitively against "<venue> <name>".
RULES: list[tuple[str, str]] = [
    # --- not language, not retrieval ---
    (r"CLEF .*(VideoCLEF|MolRec|LifeCLEF|iDPP)", OTHER),
    (r"NTCIR .*\bNAILS\b", OTHER),
    (r"FIRE .*MUSIA", OTHER),
    # --- IR that a broader rule below would otherwise claim ---
    (r"iCLEF|Interactive Track|interactive.*question answering", IR),
    (r"CLEF .*(Cultural (Heritage|micro-blog)|Grid@CLEF|Report on CLEF|Results and Approaches|Domain\s*-?\s*Specific)", IR),
    (r"CLEF .*TalentCLEF", IR),
    # Open-domain QA that finds answers in a document collection is IR in practice (as TREC
    # QA is); QA from a given text, exam or table (QA4MRE, QA Lab, SemEval QA) stays NLP.
    (r"CLEF .*(Multiple Language Question Answering|Multilingual Question Answering|ResPubliQA)", IR),
    (r"NTCIR .*(\bQAC\b|\bQAC-1\b|\bCLQA\b|Cross Lingual Question Answering)", IR),
    (r"NTCIR .*(Patent Mining|PAT MN|\bMART\b|\bSUSHI\b|\bAKG\b|VisEX|\bSS\b|Transfer)", IR),
    (r"FIRE .*(Story Illustration|SOurce COde resuse|CL-SOCO|Legal Assistance|\bAILA\b|\bCLMIR\b|\bCMIR\b)", IR),
    # --- NLP ---
    (r"question answering|\bQA\b|QA4MRE|ResPubliQA|\bQAC\b|QALab|QA Lab|CLQA|C@merata|Querying Musical", NLP),
    (r"summari[sz]|translation|\bMT\b|PatentMT|opinion|sentiment|entailment|\bRITE|MedNLP|RadNLP|HIDDEN-RAD|"
     r"\bFinNum|\bFinArg|DialEval|Short Text Conversation|\bSTC\b|\bECA\b|MedWeb|SHINRA|\bU4\b|\bUFO\b|AEOLLM", NLP),
    (r"Morpho Challenge|eRisk|EXIST|ChEMU|HIPE|ProtestNews|RepLab|Author Profiling|bioNLP|DocILE", NLP),
    # --- IR keywords (after the NLP/QA rules so "question answering" stays NLP) ---
    (r"retriev|\bsearch|ad hoc|recommend|living lab|newsreel|\bclir\b|GeoCLEF|WebCLEF|logclef|touch[eé]|argument|"
     r"dynamic search|longeval|arqmath|session|quantum|crosslink|geotime|lifelog|spoken|recipesearch|mobileclick|"
     r"1click|intent|imine|temporalia|data search|fairweb|ultre|expert|\bwww\b|openliveq|plagiarism|reuse|"
     r"\bmath\b|math-2|mathir|lilas|ll4ir|filtering|infile|RCIR|MusiCLEF|NewsImages|similar segments|soundtrack", IR),
]
_COMPILED = [(re.compile(pattern, re.IGNORECASE), label) for pattern, label in RULES]
_EXCEPTIONS = [(re.compile(pattern, re.IGNORECASE), label) for pattern, label in EXCEPTIONS]


def field_for(parent_venue: str, task_name: str) -> str:
    """Return ``NLP``, ``IR`` or ``Other`` for one task."""
    for pattern, label in _EXCEPTIONS:
        if pattern.search(f"{parent_venue} {task_name}"):
            return label
    if parent_venue in VENUE_DEFAULT:
        return VENUE_DEFAULT[parent_venue]
    if parent_venue not in MIXED_VENUES:
        return NLP
    text = f"{parent_venue} {task_name}"
    for pattern, label in _COMPILED:
        if pattern.search(text):
            return label
    # Unmatched: MediaEval is multimedia, so what is left is Other; in CLEF/NTCIR/FIRE the
    # retrieval tasks all name retrieval/search, so what is left is language processing.
    return OTHER if parent_venue == "MediaEval" else NLP
