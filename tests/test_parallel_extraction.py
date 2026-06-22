import asyncio
import unittest
from unittest.mock import patch

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
    ):
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

    def test_task_marker_is_removed_from_the_final_text(self):
        text = "[[NBX-2-abcd1234]]\nالمحتوى الكامل للفقرة."

        cleaned = SectionExtractor.remove_task_marker(
            text,
            "NBX-2-abcd1234",
        )

        self.assertEqual("المحتوى الكامل للفقرة.", cleaned)

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
