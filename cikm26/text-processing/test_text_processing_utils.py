import unittest
from unittest.mock import patch

from text_processing_utils import tokenize, tokenize_de, tokenize_en


class TokenizeEnglishTest(unittest.TestCase):
    def test_empty_text_returns_empty_list(self) -> None:
        self.assertEqual(tokenize_en(""), [])

    def test_stopword_only_text_returns_empty_list(self) -> None:
        self.assertEqual(tokenize_en("the and or but"), [])

    def test_removes_stopwords_and_stems_words(self) -> None:
        self.assertEqual(
            tokenize_en("The foxes are running quickly."),
            ["fox", "run", "quick"],
        )

    def test_removes_punctuation_and_numbers(self) -> None:
        self.assertEqual(
            tokenize_en("Cats, dogs, and 123 birds!"),
            ["cat", "dog", "bird"],
        )

    def test_normalizes_case_before_stemming(self) -> None:
        self.assertEqual(
            tokenize_en("RUNNING Running running"),
            ["run", "run", "run"],
        )

    def test_tokenizes_multiline_text(self) -> None:
        self.assertEqual(
            tokenize_en("Cats run.\nDogs jumped."),
            ["cat", "run", "dog", "jump"],
        )

    def test_removes_contraction_stopwords(self) -> None:
        self.assertEqual(tokenize_en("They aren't walking."), ["walk"])


class TokenizeGermanTest(unittest.TestCase):
    def test_empty_text_returns_empty_list(self) -> None:
        self.assertEqual(tokenize_de(""), [])

    def test_stopword_only_text_returns_empty_list(self) -> None:
        self.assertEqual(tokenize_de("der die das und oder"), [])

    def test_removes_stopwords_and_stems_words(self) -> None:
        self.assertEqual(
            tokenize_de("Die Füchse laufen sehr schnell."),
            ["fuchs", "lauf", "schnell"],
        )

    def test_removes_punctuation_and_numbers(self) -> None:
        self.assertEqual(
            tokenize_de("Katzen, Hunde und 123 Vögel!"),
            ["katz", "hund", "vogel"],
        )

    def test_normalizes_case_before_stemming(self) -> None:
        self.assertEqual(
            tokenize_de("LAUFEN Laufen laufen"),
            ["lauf", "lauf", "lauf"],
        )

    def test_tokenizes_multiline_text(self) -> None:
        self.assertEqual(
            tokenize_de("Katzen laufen.\nHunde sprangen."),
            ["katz", "lauf", "hund", "sprang"],
        )

    def test_handles_german_unicode_characters(self) -> None:
        self.assertEqual(
            tokenize_de("Größere Häuser und schöne Gärten."),
            ["gross", "haus", "schon", "gart"],
        )


class TokenizeDispatchTest(unittest.TestCase):
    @patch("text_processing_utils.tokenize_en")
    def test_forwards_english_text(self, tokenize_en_mock) -> None:
        tokenize_en_mock.return_value = ["token"]

        self.assertEqual(tokenize("Some text", "en"), ["token"])
        tokenize_en_mock.assert_called_once_with("Some text")

    @patch("text_processing_utils.tokenize_de")
    def test_forwards_german_text(self, tokenize_de_mock) -> None:
        tokenize_de_mock.return_value = ["token"]

        self.assertEqual(tokenize("Ein Text", "de"), ["token"])
        tokenize_de_mock.assert_called_once_with("Ein Text")

    def test_rejects_unsupported_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported language: fr"):
            tokenize("Du texte", "fr")

    def test_language_codes_are_case_sensitive(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported language: EN"):
            tokenize("Some text", "EN")


if __name__ == "__main__":
    unittest.main()
