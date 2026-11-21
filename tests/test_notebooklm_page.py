import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PWTimeoutError

from app.config.settings import settings
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


class StrictResponseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = NotebookLMPageClient(None)
        self.page = MagicMock()
        self.page.wait_for_timeout = AsyncMock()
        self.retry = patch(
            "app.services.notebooklm_page.NotebookLMRetryButtonHandler"
        ).start().return_value
        self.addCleanup(patch.stopall)
        self.retry.ignore_existing_buttons = AsyncMock()
        self.retry.click_if_present = AsyncMock(return_value=False)

    async def test_strict_wait_ignores_neighbour_reply_and_never_uses_latest(self):
        answer = "[[NBX-1-abc]]\nCorrect explanation."
        self.client.response_by_marker = AsyncMock(
            side_effect=["[[NBX-2-other]]\nNeighbour response.", *([answer] * 5)]
        )
        self.client.latest_response = AsyncMock(return_value="Wrong newest answer")
        with patch.object(settings, "TIMEOUT_MS", 60000):
            result = await self.client.wait_for_response(
                self.page, "NBX-1-abc", "previous", strict_marker=True
            )
        self.assertEqual(answer, result)
        self.client.latest_response.assert_not_awaited()

    async def test_strict_missing_marker_times_out_without_fallback(self):
        self.client.response_by_marker = AsyncMock(return_value="")
        self.client.latest_response = AsyncMock(return_value="Wrong answer " * 20)
        with patch.object(settings, "TIMEOUT_MS", 45000):
            with self.assertRaises(RuntimeError):
                await self.client.wait_for_response(
                    self.page, "NBX-1-abc", "previous", strict_marker=True
                )
        self.client.latest_response.assert_not_awaited()

    async def test_response_lookup_reads_only_messages_containing_request_token(self):
        matching_message = MagicMock()
        matching_message.inner_text = AsyncMock(
            return_value="[[NBX-24-own]]\nMatching Russian lesson content."
        )
        locator = MagicMock()
        locator.filter.return_value.all = AsyncMock(return_value=[matching_message])
        self.page.locator.return_value = locator
        result = await self.client.response_by_marker(
            self.page, "NBX-24-own", marker_at_start=True
        )
        self.assertEqual("[[NBX-24-own]]\nMatching Russian lesson content.", result)
        self.assertTrue(locator.filter.call_args_list)
        for call in locator.filter.call_args_list:
            self.assertEqual("NBX-24-own", call.kwargs["has_text"])
        locator.all.assert_not_called()

    async def test_slow_browser_reads_count_toward_response_timeout(self):
        self.client.response_by_marker = AsyncMock(return_value="")
        with (
            patch.object(settings, "TIMEOUT_MS", 60000),
            patch("app.services.notebooklm_page.monotonic", side_effect=[0, 61]),
        ):
            with self.assertRaises(RuntimeError):
                await self.client.wait_for_response(
                    self.page, "NBX-slow", strict_marker=True
                )
        self.client.response_by_marker.assert_awaited_once()

    async def test_strict_timeout_rejects_unstable_partial_response(self):
        self.client.response_by_marker = AsyncMock(
            side_effect=[f"[[NBX-1-abc]]\nPartial {i}" for i in range(4)]
        )
        with patch.object(settings, "TIMEOUT_MS", 12000):
            with self.assertRaises(RuntimeError):
                await self.client.wait_for_response(
                    self.page, "NBX-1-abc", strict_marker=True
                )

    async def test_strict_candidate_selection_excludes_user_prompt_and_keeps_full_answer(self):
        self.client.response_candidates = AsyncMock(return_value=[
            "Write [[NBX-1-abc]] before answering this long prompt.",
            "[[NBX-1-abc]]",
            "[[NBX-1-abc]]\nComplete English and Arabic explanation.",
            "[[NBX-2-other]]\nA different section.",
        ])
        result = await self.client.response_by_marker(
            self.page, "NBX-1-abc", marker_at_start=True
        )
        self.assertEqual("[[NBX-1-abc]]\nComplete English and Arabic explanation.", result)

    async def test_exact_request_heading_before_token_is_accepted_without_accepting_prompt(self):
        reply = "قسم من الدرس [[NBX-25-own]]\nComplete lesson explanation."
        self.client.response_candidates = AsyncMock(return_value=[
            "اكتب هوية الرد [[NBX-25-own]] في أول سطر، ثم أجب.",
            "Different heading [[NBX-25-own]]\nWrong heading.",
            "قسم من الدرس [[NBX-25-other]]\nAnother request.",
            reply,
        ])
        self.assertEqual(reply, await self.client.response_by_marker(
            self.page, "NBX-25-own", marker_at_start=True, expected_heading="قسم من الدرس"
        ))

    async def test_direction_controls_before_token_do_not_hide_own_reply(self):
        reply = "\u200f[[NBX-25-own]]\nComplete lesson explanation."
        self.client.response_candidates = AsyncMock(return_value=[reply])
        self.assertEqual(reply, await self.client.response_by_marker(
            self.page, "NBX-25-own", marker_at_start=True
        ))

    async def test_legacy_wait_still_allows_latest_response_fallback(self):
        self.client.response_by_marker = AsyncMock(return_value="")
        answer = "Unmarked legacy answer " * 10
        self.client.latest_response = AsyncMock(return_value=answer)
        with patch.object(settings, "TIMEOUT_MS", 60000):
            self.assertEqual(
                answer,
                await self.client.wait_for_response(self.page, "NBX-1-abc", "old"),
            )

    def test_request_token_cannot_match_a_prefix_or_quoted_later_instruction(self):
        self.assertFalse(self.client.has_response_marker("[[NBX-1-abc-more]]", "NBX-1-abc"))
        self.assertFalse(self.client.has_response_marker("x" * 501 + " [[NBX-1-abc]]", "NBX-1-abc"))
        self.assertTrue(self.client.has_response_marker("Heading [[NBX-1-abc]]\nBody", "NBX-1-abc"))


class PromptSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_strict_submission_reports_text_that_remains_unsent(self):
        page = MagicMock()
        page.wait_for_timeout = AsyncMock()
        chat_input = page.get_by_placeholder.return_value.first
        chat_input.count = AsyncMock(return_value=1)
        chat_input.wait_for = AsyncMock()
        chat_input.click = AsyncMock()
        chat_input.fill = AsyncMock()
        chat_input.element_handle = AsyncMock(return_value=object())
        button = page.locator.return_value.last
        button.is_visible = AsyncMock(return_value=True)
        button.is_enabled = AsyncMock(return_value=True)
        button.click = AsyncMock()
        page.wait_for_function = AsyncMock(side_effect=PWTimeoutError("input never cleared"))
        with self.assertRaisesRegex(RuntimeError, "did not submit the prompt"):
            await NotebookLMPageClient(None).send_prompt(page, "prompt", verify_sent=True)



if __name__ == "__main__":
    unittest.main()
