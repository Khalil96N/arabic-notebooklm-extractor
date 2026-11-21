import unittest
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import PromptItem
from app.services.section_extractor import SectionExtractor


COMPLETE_COMBINED_RESPONSE = (
    "<letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>"
    "<rules_section>لا توجد قاعدة جديدة في هذا الجزء.</rules_section>"
    "<dialogues_section>لا يوجد حوار تعليمي في هذا الجزء.</dialogues_section>"
    "<vocabulary_section></vocabulary_section>"
)


class IsFailedResponseTests(unittest.TestCase):
    def test_empty_text_is_failed_regardless_of_prompt_kind(self):
        self.assertTrue(SectionExtractor.is_failed_response(""))

    def test_known_failure_phrase_is_failed(self):
        self.assertTrue(
            SectionExtractor.is_failed_response(
                "I'm having trouble responding right now."
            )
        )

    def test_complete_combined_response_is_not_failed(self):
        prompt_item = PromptItem(
            heading="قسم من الدرس",
            prompt_text="...",
            output_kind="combined",
        )

        self.assertFalse(
            SectionExtractor.is_failed_response(
                COMPLETE_COMBINED_RESPONSE, prompt_item
            )
        )

    def test_combined_response_missing_a_section_tag_is_failed(self):
        prompt_item = PromptItem(
            heading="قسم من الدرس",
            prompt_text="...",
            output_kind="combined",
        )
        incomplete_response = (
            "<letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>"
            "<dialogues_section>لا يوجد حوار تعليمي في هذا الجزء.</dialogues_section>"
            "<vocabulary_section></vocabulary_section>"
        )

        self.assertTrue(
            SectionExtractor.is_failed_response(
                incomplete_response, prompt_item
            )
        )

    def test_non_combined_prompt_ignores_missing_section_tags(self):
        prompt_item = PromptItem(
            heading="الخلاصة والواجب",
            prompt_text="...",
            output_kind="summary",
        )
        recap_text = "<subheading>الخلاصة والواجب</subheading> نص طويل بما يكفي."

        self.assertFalse(
            SectionExtractor.is_failed_response(recap_text, prompt_item)
        )


class CompleteCumulativeResultsTests(unittest.TestCase):
    def test_incomplete_russian_job_raises_before_export(self):
        prompts = [
            PromptItem(
                heading="قسم من الدرس",
                prompt_text="...",
                output_kind="combined",
            ),
            PromptItem(
                heading="الخلاصة والواجب",
                prompt_text="...",
                output_kind="summary",
            ),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "Existing cumulative files were left unchanged",
        ):
            SectionExtractor.raise_for_incomplete_cumulative_results(
                prompts,
                [COMPLETE_COMBINED_RESPONSE, None],
            )

    def test_complete_russian_job_is_accepted(self):
        prompts = [
            PromptItem(
                heading="قسم من الدرس",
                prompt_text="...",
                output_kind="combined",
            ),
        ]

        SectionExtractor.raise_for_incomplete_cumulative_results(
            prompts,
            [COMPLETE_COMBINED_RESPONSE],
        )

    def test_arabic_best_effort_behavior_is_unchanged(self):
        prompts = [
            PromptItem(
                heading="قسم عربي",
                prompt_text="...",
                output_kind="summary",
            ),
        ]

        SectionExtractor.raise_for_incomplete_cumulative_results(
            prompts,
            [None],
        )


class EnglishMarkerRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mismatched_reply_is_retried_with_new_id_and_id_is_removed(self):
        client = MagicMock()
        client.latest_response = AsyncMock(return_value="Previous response")
        client.send_prompt = AsyncMock()
        observed = []

        async def answer(_page, **kwargs):
            observed.append(kwargs)
            if len(observed) == 1:
                return "[[NBX-neighbour]]\nWrong section content"
            if len(observed) == 2:
                return f"[[{kwargs['marker']}]]\n<subheading>Heading without explanation</subheading>"
            return f"[[{kwargs['marker']}]]\nCorrect section content"

        client.wait_for_response = AsyncMock(side_effect=answer)
        extractor = SectionExtractor(None, client, None, "url", "lecture")
        extractor.RETRY_DELAY_SECONDS = 0
        result = await extractor.extract_with_retries(
            None, PromptItem(heading="Topic", prompt_text="Explain"),
            "NBX-first", strict_marker=True,
        )
        self.assertEqual("Correct section content", result)
        self.assertEqual(3, len(observed))
        self.assertEqual(3, len({item["marker"] for item in observed}))
        self.assertTrue(all(item["strict_marker"] for item in observed))
        sent = client.send_prompt.await_args_list
        for call, options in zip(sent, observed):
            self.assertIn(f"[[{options['marker']}]]", call.args[1])


class RussianMarkerRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_neighbour_and_incomplete_chunk_before_accepting_matching_reply(self):
        client = MagicMock()
        client.latest_response = AsyncMock(return_value="Previous response")
        client.send_prompt = AsyncMock()
        observed = []

        async def answer(_page, **kwargs):
            observed.append(kwargs)
            if len(observed) == 1:
                return "[[NBX-neighbour]]\n" + COMPLETE_COMBINED_RESPONSE
            if len(observed) == 2:
                return (
                    f"[[{kwargs['marker']}]]\n"
                    "<letters_section>حرف جديد</letters_section>"
                )
            return f"[[{kwargs['marker']}]]\n" + COMPLETE_COMBINED_RESPONSE

        client.wait_for_response = AsyncMock(side_effect=answer)
        extractor = SectionExtractor(None, client, None, "url", "lecture")
        extractor.RETRY_DELAY_SECONDS = 0
        result = await extractor.extract_with_retries(
            None,
            PromptItem(heading="مقطع روسي", prompt_text="استخرج", output_kind="combined"),
            "NBX-first-russian",
            strict_marker=True,
        )
        self.assertEqual(COMPLETE_COMBINED_RESPONSE, result)
        self.assertEqual(3, len(observed))
        self.assertEqual(3, len({item["marker"] for item in observed}))
        self.assertTrue(all(item["strict_marker"] for item in observed))
        for call, options in zip(client.send_prompt.await_args_list, observed):
            self.assertTrue(call.kwargs["verify_sent"])
            self.assertIn(f"[[{options['marker']}]]", call.args[1])


if __name__ == "__main__":
    unittest.main()
