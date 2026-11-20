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
