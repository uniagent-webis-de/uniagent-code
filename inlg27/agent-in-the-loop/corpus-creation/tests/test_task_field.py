from src.task_field import field_for


def test_venue_defaults():
    assert field_for("TREC", "Fair Ranking") == "IR"
    assert field_for("SemEval", "Sentiment Analysis in Twitter") == "NLP"
    assert field_for("CoNLL", "Chunking") == "NLP"


def test_mixed_venues_label_by_subject_not_venue():
    assert field_for("CLEF", "Touché 2021: Argument Retrieval") == "IR"
    assert field_for("CLEF", "QA4MRE") == "NLP"
    assert field_for("CLEF", "iCLEF 2004 Track Overview: Interactive Cross-Language Question Answering") == "IR"
    assert field_for("CLEF", "The Domain -Specific Track") == "IR"
    assert field_for("CLEF", "LifeCLEF 2014 Fish Task") == "Other"
    assert field_for("NTCIR", "WWW-3") == "IR"
    assert field_for("NTCIR", "QA Lab-PoliInfo-2") == "NLP"
    assert field_for("FIRE", "Hate Speech and Offensive Content Identification") == "NLP"
    assert field_for("FIRE", "Information Retrieval from Microblogs during Disasters") == "IR"
    assert field_for("MediaEval", "Retrieving Diverse Social Images") == "IR"
    assert field_for("MediaEval", "Visual Privacy: Preserving Privacy in Surveillance Videos") == "Other"


def test_corpus_qa_is_ir_but_reading_comprehension_qa_is_nlp():
    assert field_for("CLEF", "CLEF 2005 Multilingual Question Answering Track") == "IR"
    assert field_for("CLEF", "ResPubliQA 2010: Question Answering Evaluation over European Legislation") == "IR"
    assert field_for("NTCIR", "Cross Lingual Question Answering Task (CLQA)") == "IR"
    assert field_for("NTCIR", "QAC") == "IR"
    assert field_for("CLEF", "QA4MRE") == "NLP"
    assert field_for("CLEF", "CLEF QA Entrance Exams Task 2015") == "NLP"
    assert field_for("NTCIR", "QA Lab-PoliInfo-2") == "NLP"
    assert field_for("SemEval", "Community Question Answering") == "NLP"


def test_confirmed_exceptions():
    assert field_for("FIRE", "Information Retrieval in Software Engineering (IRSE)") == "NLP"
    assert field_for("FIRE", "IRSE") == "NLP"
    assert field_for("SemEval", "Multilingual and Crosslingual Fact-Checked Claim Retrieval") == "IR"
    assert field_for("TREC", "Incident Streams") == "NLP"
    assert field_for("CLEF", "LeQua@CLEF 2022: Learning to Quantify") == "NLP"
