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

    def test_source_match_is_hamza_and_digit_insensitive(self):
        target = "اداب العلم ١٤"
        candidate = "video_audio_call\nالفصل (1,2,3) - آداب طلب العلم 14.mp3"

        self.assertTrue(source_names_match(target, candidate))

    def test_normalized_source_converts_arabic_indic_digits(self):
        self.assertEqual("ادابالعلم14", normalize_source_name("آداب العلم ١٤"))

    def test_page_client_keeps_legacy_source_match_entry_point(self):
        self.assertTrue(
            NotebookLMPageClient._source_matches(
                "آداب العلم 14",
                "الفصل (1,2,3) - آداب طلب العلم 14.mp3",
            )
        )


if __name__ == "__main__":
    unittest.main()
