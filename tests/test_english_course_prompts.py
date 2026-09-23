import unittest
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import ExtractionItem
from app.prompts.english_course_templates import (
    build_boundary_context,
    build_outline_prompt,
)
from app.prompts.generator import PromptGenerator
from app.prompts.profiles import get_prompt_profile, validate_content_type
from app.services.notebooklm import NotebookLMService


class EnglishCoursePromptTests(unittest.TestCase):
    def test_outline_prompt_targets_only_the_selected_lecture(self):
        prompt = build_outline_prompt("02. Introduction")

        self.assertIn("02. Introduction", prompt)
        self.assertIn("مصدر الفيديو الإنجليزي المحدد فقط", prompt)

    def test_boundary_context_keeps_english_source_phrases(self):
        context = build_boundary_context(
            "Let us define a perceptron",
            "Now we move to higher dimensions",
        )

        self.assertIn("Let us define a perceptron", context)
        self.assertIn("Now we move to higher dimensions", context)

    def test_empty_boundaries_do_not_add_boundary_instruction(self):
        self.assertEqual("", build_boundary_context(None, None))

    def test_english_profile_routes_outline_and_section_prompts(self):
        outline = get_prompt_profile("english").build_outline_prompt(
            "02. Introduction",
            None,
        )
        prompts = PromptGenerator.generate_prompts(
            [ExtractionItem(title="خاتمة النموذج", level=1)],
            "english",
        )
        section = prompts[0].prompt_text

        self.assertIn("مصدر الفيديو الإنجليزي المحدد فقط", outline)
        self.assertIn("<english>", section)
        self.assertIn("الشرح والإضافات بالعربية", section)
        self.assertNotIn("بسم الله", section)
        self.assertNotIn("بما أن هذه الفقرة هي خاتمة المحاضرة", section)

    def test_arabic_is_the_default_prompt_profile(self):
        prompt = PromptGenerator.generate_prompts(
            [ExtractionItem(title="القسم الأول", level=1)]
        )[0].prompt_text

        self.assertIn("مقدمة الشارح", prompt)
        self.assertNotIn("<english>", prompt)

    def test_content_type_validation_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "arabic.*english.*russian"):
            validate_content_type("automatic")


class EnglishCourseServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_uses_the_selected_english_outline(self):
        page = MagicMock()
        page.url = "https://notebooklm.google.com/notebook/example"
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        service = NotebookLMService(context)
        service.page_client = MagicMock()
        service.page_client.open_configured_notebook = AsyncMock()
        service.page_client.send_prompt = AsyncMock()
        service.page_client.wait_for_response = AsyncMock(
            return_value="[[رئيسي: أولاً: Introduction]]"
        )

        await service.discover_extraction_plan(
            "Deep Learning",
            "02. Introduction",
            content_type="english",
        )

        sent_prompt = service.page_client.send_prompt.await_args.args[1]
        self.assertIn("مصدر الفيديو الإنجليزي المحدد فقط", sent_prompt)
        self.assertNotIn("حلّل المحاضرة كاملة", sent_prompt)


if __name__ == "__main__":
    unittest.main()
