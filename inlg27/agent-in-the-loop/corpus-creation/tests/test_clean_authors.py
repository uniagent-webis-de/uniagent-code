from src.clean_authors import clean_authors, clean_title


def test_joined_string_with_affiliation_is_split():
    assert clean_authors(["Jikang Xiao, Shigen Jiang and Yaojun Niu - Cognitive Computing Group"]) == ["Jikang Xiao", "Shigen Jiang", "Yaojun Niu"]


def test_affiliation_only_and_junk_entries_are_dropped():
    assert clean_authors(["Hui Fang", "University of Delaware", "(function(){var a=1;})();"]) == ["Hui Fang"]


def test_parenthesised_affiliation_removed_and_entities_decoded():
    assert clean_authors(["Jan Bakker (University of Amsterdam)Jaap Kamps (University of Amsterdam)"]) == ["Jan Bakker", "Jaap Kamps"]
    assert clean_authors(["Fuat C. Beylunio&gbreve;lu"]) == ["Fuat C. Beylunioğlu"]


def test_single_token_and_surname_first_entries_survive():
    assert clean_authors(["Madhumitha.M", "SATO, Takashi"]) == ["Madhumitha.M", "SATO, Takashi"]


def test_title_loses_page_range_and_trailing_author_list():
    assert clean_title("Word Spaces as Input Jussi Karlgren pp.263-264", ["Jussi Karlgren"]) == "Word Spaces as Input"
    assert clean_title("Opinion Analysis at POSTECH Hun-Young Jung, Jungi Kim and Jong-Hyeok Lee pp.258-262", ["Hun-Young Jung"]) == "Opinion Analysis at POSTECH"
    assert clean_title("Overview of the Task", ["Someone Else"]) == "Overview of the Task"
