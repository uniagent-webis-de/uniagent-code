from collections.abc import Callable

from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from nltk.tokenize import word_tokenize

_ENGLISH_STOPWORDS = frozenset(stopwords.words("english"))
_GERMAN_STOPWORDS = frozenset(stopwords.words("german"))
_ENGLISH_STEMMER = SnowballStemmer("english")
_GERMAN_STEMMER = SnowballStemmer("german")


def _tokenize(
    text: str,
    language: str,
    language_stopwords: frozenset[str],
    stem: Callable[[str], str],
) -> list[str]:
    words = word_tokenize(text.lower(), language=language)
    return [
        stem(word)
        for word in words
        if word.isalpha() and word not in language_stopwords
    ]


def tokenize_en(text: str) -> list[str]:
    return _tokenize(
        text,
        language="english",
        language_stopwords=_ENGLISH_STOPWORDS,
        stem=_ENGLISH_STEMMER.stem,
    )


def tokenize_de(text: str) -> list[str]:
    return _tokenize(
        text,
        language="german",
        language_stopwords=_GERMAN_STOPWORDS,
        stem=_GERMAN_STEMMER.stem,
    )


def tokenize(text: str, language: str) -> list[str]:
    tokenizers = {
        "en": tokenize_en,
        "de": tokenize_de,
    }

    try:
        tokenizer = tokenizers[language]
    except KeyError:
        raise ValueError(f"Unsupported language: {language}") from None

    return tokenizer(text)
