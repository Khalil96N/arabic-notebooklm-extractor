import unittest

from app.services.notebooklm_page import NotebookLMPageClient
from app.utils.source_names import normalize_source_name, source_names_match


class NotebookLMPageMatchingTests(unittest.TestCase):
    def test_source_match_allows_extra_words_in_candidate(self):
        target = "آداب العلم 14"
        candidate = "video_audio_call\nالفصل (1,2,3) - آداب طلب العلم 14.mp3"

        self.assertTrue(source_names_match(target, candidate))

    def test_source_match_keeps_lecture_number_specific(self):
        target = "آداب العلم 15"
        candidate = "video_audio_call\nالفصل (1,2,3) - آداب طلب العلم 14.mp3"

        self.assertFalse(source_names_match(target, candidate))

    def test_source_match_does_not_treat_one_as_prefix_of_ten(self):
        target = "video_audio_call ПОД-154Т (10).mp3"
        wrong_candidate = "video_audio_call\nПОД-154Т (1).mp3"
        correct_candidate = "video_audio_call\nПОД-154Т (10).mp3"

        self.assertFalse(source_names_match(target, wrong_candidate))
        self.assertTrue(source_names_match(target, correct_candidate))

    def test_source_match_is_hamza_and_digit_insensitive(self):
        target = "اداب العلم ١٤"
        candidate = "video_audio_call\nالفصل (1,2,3) - آداب طلب العلم 14.mp3"

        self.assertTrue(source_names_match(target, candidate))

    def test_normalized_source_converts_arabic_indic_digits(self):
        self.assertEqual("ادابالعلم14", normalize_source_name("آداب العلم ١٤"))

    def test_english_source_does_not_match_an_earlier_numeric_collision(self):
        target = "09. AND And OR Perceptrons"
        wrong_candidate = (
            "video_audio_call\n"
            "06. 09 Higher Dimensions-eBHunImDmWw.mp4"
        )
        correct_candidate = (
            "video_audio_call\n"
            "09. AND And OR Perceptrons-45K5N0P9wJk.mp4"
        )

        self.assertFalse(source_names_match(target, wrong_candidate))
        self.assertTrue(source_names_match(target, correct_candidate))

    def test_page_client_keeps_legacy_source_match_entry_point(self):
        self.assertTrue(
            NotebookLMPageClient._source_matches(
                "آداب العلم 14",
                "الفصل (1,2,3) - آداب طلب العلم 14.mp3",
            )
        )

    def test_clean_response_text_drops_only_leading_ui_artifacts(self):
        self.assertEqual(
            "[[رئيسي: أولاً: بداية الدرس]]",
            NotebookLMPageClient.clean_response_text(
                "Thoughts\nexpand_more\n[[رئيسي: أولاً: بداية الدرس]]"
            ),
        )

    def test_clean_response_text_returns_empty_for_only_ui_artifacts(self):
        self.assertEqual(
            "",
            NotebookLMPageClient.clean_response_text("Thoughts\nexpand_more"),
        )


if __name__ == "__main__":
    unittest.main()
