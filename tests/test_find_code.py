from src.find_code import clean_url, extract_links, pdf_filename_for

SAMPLE_TEXT = """
Our code is available at https://github.com/team-x/repo-name.git and the
dataset can be found on https://zenodo.org/record/1234567 (accessed 2023).
We also used the TIRA platform, see https://www.tira.io/task/example/.
Docker image: docker.io/webis/example-image:1.0.
"""


def test_extracts_github_and_zenodo_urls():
    code_urls, _ = extract_links(SAMPLE_TEXT)
    assert "https://github.com/team-x/repo-name.git" in code_urls
    assert "https://zenodo.org/record/1234567" in code_urls


def test_extracts_tira_url_and_docker_image():
    _, tira_refs = extract_links(SAMPLE_TEXT)
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
    code_urls, tira_refs = extract_links("This paper has no code or data links at all.")
    assert code_urls == []
    assert tira_refs == []
