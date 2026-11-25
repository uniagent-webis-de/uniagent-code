from src.paper_links import canonical_link, document_links

TEXT = """# Paper
Our code is at [link](https://github.com/team/system/tree/main) and the data at
https://huggingface.co/datasets/org/corpus. We fine-tuned https://huggingface.co/org/model-x,
see also https://www.kaggle.com/datasets/own/set1 and https://tira.io/task/foo/.
Zenodo release of the annotated corpus: https://zenodo.org/records/123.
"""
TEXT += "filler text. " * 200 + "\n## References\nhttps://github.com/cited/only\n"


def test_kinds_and_reference_flag():
    links = {link["url"]: link for link in document_links(TEXT, {"https://github.com/team/system": 0.9})}
    assert links["https://github.com/team/system"]["kind"] == "code"
    assert links["https://github.com/team/system"]["own_code_score"] == 0.9
    assert links["https://huggingface.co/datasets/org/corpus"]["kind"] == "dataset"
    assert links["https://huggingface.co/org/model-x"]["kind"] == "model"
    assert links["https://www.kaggle.com/datasets/own/set1"]["kind"] == "dataset"
    assert links["https://zenodo.org/records/123"]["kind"] == "dataset"
    assert links["https://tira.io/task/foo/"]["kind"] == "tira"
    assert links["https://github.com/cited/only"]["in_references"] is True
    assert links["https://github.com/team/system"]["in_references"] is False


def test_third_party_flag_and_bare_links_dropped():
    links = document_links("https://github.com/huggingface/transformers and https://github.com/someone")
    assert [(l["url"], l["third_party"]) for l in links] == [("https://github.com/huggingface/transformers", True)]
    assert canonical_link("https://www.kaggle.com/datasets/own") is None
def test_curated_github_datasets_are_not_labelled_code():
    from src.paper_links import document_links

    links = document_links("Data: https://github.com/m-popovic/QRev-annotations "
                           "https://github.com/harvardnlp/boxscore-data "
                           "https://github.com/WebNLG/challenge-2020")
    assert [link["kind"] for link in links] == ["dataset", "dataset", "dataset"]


def test_links_index_uses_complete_fenced_footnote_url():
    from src.paper_links import document_links

    links = document_links("```\n1 https://github.com/skoltech-nlp/feedback_\ngeneration_nigula\n```")
    assert links[0]["url"] == "https://github.com/skoltech-nlp/feedback_generation_nigula"


def test_dataset_names_do_not_override_reviewed_implementation_evidence():
    links = document_links("https://github.com/ufal/automin-2023-data "
        "https://github.com/IBM/mt-rag-benchmark "
        "https://github.com/shrsijan/mt-rag-benchmark "
        "https://github.com/ufoym/imbalanced-dataset-sampler")
    assert [link["kind"] for link in links] == ["dataset", "dataset", "code", "code"]
