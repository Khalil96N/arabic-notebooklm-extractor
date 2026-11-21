import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.config.settings import settings
from app.models.schemas import PromptItem
from app.services.section_extractor import SectionExtractor


class FakePage:
    def __init__(self):
        self.closed = False

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


class ParallelSectionExtractor(SectionExtractor):
    def __init__(self):
        self.context = None
        self.page_client = None
        self.current_page = FakePage()
        self.notebook_url = "https://notebooklm.google.com/notebook/test"
        self.notebook_name = "دفتر"
        self.lecture_name = "محاضرة"
        self.book_name = None
        self.active_requests = 0
        self.max_active_requests = 0
        self.worker_pages = []
        self.request_options = []

    async def prepare_worker_tabs(self, worker_count: int) -> list:
        self.worker_pages = [self.current_page] + [
            FakePage()
            for _ in range(worker_count - 1)
        ]
        return self.worker_pages

    async def extract_with_retries(
        self,
        page,
        prompt_item,
        marker=None,
        *,
        strict_marker=False,
    ):
        self.request_options.append((marker, strict_marker))
        self.active_requests += 1
        self.max_active_requests = max(
            self.max_active_requests,
            self.active_requests,
        )
        try:
            delay = {
                "أولاً": 0.06,
                "ثانياً": 0.01,
                "ثالثاً": 0.03,
            }[prompt_item.heading]
            await asyncio.sleep(delay)
            return f"نص {prompt_item.heading}"
        finally:
            self.active_requests -= 1


class ParallelExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_tabs_run_in_parallel_and_return_in_original_order(self):
        service = ParallelSectionExtractor()
        prompts = [
            PromptItem(heading="أولاً", prompt_text="الأول"),
            PromptItem(heading="ثانياً", prompt_text="الثاني"),
            PromptItem(heading="ثالثاً", prompt_text="الثالث"),
        ]

        with (
            patch.object(settings, "PARALLEL_EXTRACTIONS", 3),
            patch(
                "app.services.section_extractor."
                "FileExporter.save_word_document"
            ) as save_word,
        ):
            sections = await service.extract(prompts, "اختبار")

        self.assertGreaterEqual(service.max_active_requests, 2)
        self.assertEqual(
            [
                ("أولاً", "نص أولاً"),
                ("ثانياً", "نص ثانياً"),
                ("ثالثاً", "نص ثالثاً"),
            ],
            sections,
        )
        self.assertGreaterEqual(save_word.call_count, 1)
        self.assertTrue(all(page.closed for page in service.worker_pages))

    async def test_russian_chunks_and_recap_use_three_tabs_with_strict_matching(self):
        service = ParallelSectionExtractor()
        prompts = [
            PromptItem(
                heading="أولاً",
                prompt_text="الأول",
                output_kind="combined",
            ),
            PromptItem(
                heading="ثانياً",
                prompt_text="الثاني",
                output_kind="combined",
            ),
            PromptItem(
                heading="ثالثاً",
                prompt_text="الثالث",
                output_kind="summary",
            ),
        ]

        with (
            patch.object(settings, "PARALLEL_EXTRACTIONS", 3),
            patch(
                "app.services.section_extractor."
                "FileExporter.save_word_document"
            ) as save_word,
        ):
            sections = await service.extract(prompts, "اختبار")

        self.assertEqual(3, service.max_active_requests)
        self.assertEqual(3, len(service.worker_pages))
        self.assertTrue(all(marker and strict for marker, strict in service.request_options))
        self.assertEqual(3, len({marker for marker, _ in service.request_options}))
        self.assertEqual(
            [
                ("أولاً", "نص أولاً"),
                ("ثانياً", "نص ثانياً"),
                ("ثالثاً", "نص ثالثاً"),
            ],
            sections,
        )
        save_word.assert_not_called()
        self.assertTrue(all(page.closed for page in service.worker_pages))

    async def test_russian_recovery_keeps_strict_matching_and_blocks_partial_export(self):
        service = ParallelSectionExtractor()
        service.extract_with_retries = AsyncMock(
            side_effect=[None, None, "recovered", None]
        )
        prompts = [
            PromptItem(heading="أولاً", prompt_text="مقطع", output_kind="combined"),
            PromptItem(heading="ثانياً", prompt_text="الخلاصة", output_kind="summary"),
        ]
        with (
            patch.object(settings, "PARALLEL_EXTRACTIONS", 3),
            patch("app.services.section_extractor.FileExporter.save_word_document") as save_word,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Existing cumulative files were left unchanged"
            ):
                await service.extract(prompts, "test")

        calls = service.extract_with_retries.await_args_list
        self.assertEqual(2, len(service.worker_pages))
        self.assertEqual(4, len(calls))
        self.assertTrue(all(call.kwargs["strict_marker"] for call in calls))
        markers = [
            call.args[2] if len(call.args) > 2 else call.kwargs["marker"]
            for call in calls
        ]
        self.assertTrue(all(markers))
        self.assertEqual(4, len(set(markers)))
        save_word.assert_not_called()
        self.assertTrue(all(page.closed for page in service.worker_pages))

    async def test_english_course_uses_three_tabs_and_preserves_original_order(self):
        service = ParallelSectionExtractor()
        prompts = [
            PromptItem(heading="أولاً", prompt_text="الأول"),
            PromptItem(heading="ثانياً", prompt_text="الثاني"),
            PromptItem(
                heading="ثالثاً",
                prompt_text="المواعيد",
                output_kind="logistics",
            ),
        ]

        with (
            patch.object(settings, "PARALLEL_EXTRACTIONS", 3),
            patch(
                "app.services.section_extractor."
                "FileExporter.save_word_document"
            ) as save_word,
        ):
            sections = await service.extract(prompts, "اختبار")

        self.assertEqual(3, service.max_active_requests)
        self.assertEqual(3, len(service.worker_pages))
        self.assertTrue(all(marker and strict for marker, strict in service.request_options))
        self.assertEqual(3, len({marker for marker, _ in service.request_options}))
        self.assertEqual(
            [
                ("أولاً", "نص أولاً"),
                ("ثانياً", "نص ثانياً"),
                ("ثالثاً", "نص ثالثاً"),
            ],
            sections,
        )
        self.assertGreaterEqual(save_word.call_count, 1)
        self.assertTrue(service.worker_pages[0].closed)

    def test_task_marker_is_removed_from_the_final_text(self):
        text = "[[NBX-2-abcd1234]]\nالمحتوى الكامل للفقرة."

        cleaned = SectionExtractor.remove_task_marker(
            text,
            "NBX-2-abcd1234",
        )

        self.assertEqual("المحتوى الكامل للفقرة.", cleaned)

    async def test_english_fallback_keeps_strict_matching_and_reports_final_failure(self):
        from unittest.mock import AsyncMock

        service = ParallelSectionExtractor()
        service.extract_with_retries = AsyncMock(side_effect=[None, None, "recovered", None])
        prompts = [
            PromptItem(heading="أولاً", prompt_text="شرح"),
            PromptItem(heading="ثانياً", prompt_text="مواعيد", output_kind="logistics"),
        ]
        with patch("app.services.section_extractor.FileExporter.save_word_document"):
            with self.assertRaisesRegex(RuntimeError, "English extraction is incomplete.*ثانياً"):
                await service.extract(prompts, "test")
        calls = service.extract_with_retries.await_args_list
        self.assertEqual(2, len(service.worker_pages))
        self.assertEqual(4, len(calls))
        self.assertTrue(all(call.kwargs["strict_marker"] for call in calls))
        markers = [call.args[2] if len(call.args) > 2 else call.kwargs["marker"] for call in calls]
        self.assertEqual(4, len(set(markers)))
        self.assertTrue(all(page.closed for page in service.worker_pages))

    def test_task_marker_is_removed_after_the_visible_heading(self):
        text = (
            "رابعاً: عنوان الفقرة [[NBX-RETRY-a646bb52ec]]\n"
            "المحتوى الكامل للفقرة."
        )

        cleaned = SectionExtractor.remove_task_marker(
            text,
            "NBX-RETRY-a646bb52ec",
        )

        self.assertEqual(
            "رابعاً: عنوان الفقرة المحتوى الكامل للفقرة.",
            cleaned,
        )


if __name__ == "__main__":
    unittest.main()
