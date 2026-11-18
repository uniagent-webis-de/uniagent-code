from src.find_code import (
    clean_url,
    extract_links,
    is_third_party,
    pdf_filename_for,
    strip_bibliography,
    canonical_repo_url,
)

SAMPLE_TEXT = """
Our code is available at https://github.com/team-x/repo-name.git and the
dataset can be found on https://zenodo.org/record/1234567 (accessed 2023).
We also used the TIRA platform, see https://www.tira.io/task/example/.
Docker image: docker.io/webis/example-image:1.0.
"""


def test_extracts_team_code_and_zenodo_urls():
    code, _, _ = extract_links(SAMPLE_TEXT)
    urls = [c["url"] for c in code]
    assert "https://github.com/team-x/repo-name" in urls
    assert "https://zenodo.org/records/1234567" in urls


def test_extracts_tira_url_and_docker_image():
    _, _, tira_refs = extract_links(SAMPLE_TEXT)
    assert "https://www.tira.io/task/example/" in tira_refs
    assert "docker.io/webis/example-image:1.0" in tira_refs


def test_clean_url_strips_trailing_sentence_punctuation():
    assert clean_url("https://github.com/x/y.") == "https://github.com/x/y"
    assert clean_url("https://github.com/x/y),") == "https://github.com/x/y"
    assert clean_url("https://github.com/x/y") == "https://github.com/x/y"


def test_pdf_filename_derived_from_url_path():
    assert pdf_filename_for("https://ceur-ws.org/Vol-2696/paper_130.pdf") == "paper_130"
    assert pdf_filename_for("https://ceur-ws.org/Vol-3497/paper-053.pdf") == "paper-053"


def test_no_links_returns_empty_lists():
    code, third, tira = extract_links("This paper has no code or data links at all.")
    assert code == [] and third == [] and tira == []


def test_third_party_dependencies_are_classified_not_stored_as_team_code():
    # Real data problem found in audit: ~48% of stored code_urls were shared
    # infrastructure the team merely used, presented as their submission.
    for url in [
        "https://github.com/huggingface/transformers",
        "https://github.com/nltk/nltk",
        "https://github.com/fchollet/keras",
        "https://github.com/usnistgov/trec_eval",
        "https://huggingface.co/meta-llama/Llama-2-7b",
        "https://huggingface.co/bert-base-uncased",
    ]:
        assert is_third_party(url) is True, url
    for url in [
        "https://github.com/team-x/my-clef-submission",
        "https://github.com/jmloyola/erisk-2021",
        "https://huggingface.co/dsgt-arc/checkthat-subjectivity",
    ]:
        assert is_third_party(url) is False, url


def test_third_party_links_are_kept_separately_not_silently_dropped():
    text = "We fine-tuned https://github.com/huggingface/transformers and release ours at https://github.com/teamq/sub."
    code, third, _ = extract_links(text)
    assert [c["url"] for c in code] == ["https://github.com/teamq/sub"]
    assert third == ["https://github.com/huggingface/transformers"]


def test_bibliography_is_excluded_from_matching():
    # A paper's reference list cites the tools it used; those are not the team's code.
    text = (
        "Introduction. We release our system at https://github.com/teamq/sub.\n"
        + "filler line\n" * 60
        + "References\n"
        + "[1] Wolf et al. https://github.com/some-lab/cited-tool\n"
    )
    code, _, _ = extract_links(text)
    urls = [c["url"] for c in code]
    assert "https://github.com/teamq/sub" in urls
    assert "https://github.com/some-lab/cited-tool" not in urls


def test_in_body_mention_of_references_does_not_truncate_the_paper():
    text = "References to prior work follow.\n" + "body\n" * 40 + "We release https://github.com/teamq/sub here.\n"
    assert "github.com/teamq/sub" in strip_bibliography(text)


def test_availability_evidence_flag_distinguishes_released_code_from_passing_mention():
    released = "Our code is available at https://github.com/teamq/sub for reproducibility."
    mention = "We compared against the approach of https://github.com/otherlab/thing in Table 3."
    assert extract_links(released)[0][0]["evidence"] is True
    assert extract_links(mention)[0][0]["evidence"] is False


def test_canonical_repo_url_normalises_and_rejects_non_repos():
    assert canonical_repo_url("http://www.github.com/a/b.git") == "https://github.com/a/b"
    assert canonical_repo_url("https://github.com/NUSTM/X/tree/main/Cod") == "https://github.com/NUSTM/X"
    assert canonical_repo_url("https://huggingface.co/datasets/o/d/viewer") == "https://huggingface.co/datasets/o/d"
    for non_repo in ("https://github.com/percyliang/", "https://huggingface.co/",
                     "https://huggingface.co/transformers/pretrained_models.html", "https://github.com/*"):
        assert canonical_repo_url(non_repo) is None


def test_extract_links_survives_markdown_debris():
    text = "Code: [https://github.com/a/b](https://github.com/a/b). Also https://github.com/x/my\\_repo) end."
    urls = [c["url"] for c in extract_links(text)[0]]
    assert urls == ["https://github.com/a/b", "https://github.com/x/my_repo"]


def test_markdown_link_href_beats_wrapped_visible_text():
    text = "[https://github.com/K/Sem23\\_](https://github.com/K/Sem23_Legal_Team)\n\n[Legal\\_Team](https://github.com/K/Sem23_Legal_Team)"
    assert [c["url"] for c in extract_links(text)[0]] == ["https://github.com/K/Sem23_Legal_Team"]


def test_truncated_fragment_is_superseded_by_full_url_and_angle_href_is_read():
    text = "see https://github.com/h/sem26_task10_ and [x](https://github.com/h/sem26_task10_starter_pack) plus [y](< https://github.com/a/b >)"
    urls = [c["url"] for c in extract_links(text)[0]]
    assert urls == ["https://github.com/a/b", "https://github.com/h/sem26_task10_starter_pack"]
