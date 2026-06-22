import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.settings import settings
from app.models.schemas import ExtractionItem
from app.prompts.generator import PromptGenerator
from app.prompts.templates import build_outline_prompt
from app.workflow import next_output_name


class WorkflowTests(unittest.TestCase):
    def test_outline_prompt_only_requests_the_extraction_plan(self):
        prompt = build_outline_prompt("المحاضرة", "الكتاب")

        self.assertIn("المحاضرة", prompt)
        self.assertIn("الكتاب", prompt)
        self.assertIn("[[رئيسي: أولاً:", prompt)
        self.assertIn("[[سؤال ختامي: نص السؤال]]", prompt)
        self.assertIn("لا تكتب التفريغ الكامل", prompt)
        self.assertIn("لا تكتب جواب السؤال أو محتوى أي قسم", prompt)

    def test_outline_prompt_scales_heading_count_for_long_lectures(self):
        prompt = build_outline_prompt("محاضرة طويلة")

        self.assertIn("ساعة ونصفاً (90 دقيقة)", prompt)
        self.assertIn("15-20 دقيقة", prompt)
        self.assertIn("ساعتين (120 دقيقة)", prompt)
        self.assertIn("12-15 دقيقة", prompt)
        self.assertIn("8-12 عنواناً", prompt)

    def test_outline_prompt_source_context_keeps_instruction_numbering(self):
        prompt = build_outline_prompt("المحاضرة", "الكتاب")

        self.assertIn("9- المصدر الأساسي المطلوب تحليله", prompt)

    def test_detail_prompts_tag_literal_book_readings_as_matn(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="القسم الرئيس", level=1),
                ExtractionItem(
                    title="ما نص المسألة؟",
                    level=2,
                    kind="end_question",
                ),
            ]
        )

        for prompt in prompts:
            self.assertIn("<matn>", prompt.prompt_text)
            self.assertIn("</matn>", prompt.prompt_text)
            self.assertIn("نصاً حرفياً من الكتاب أو المتن", prompt.prompt_text)

    def test_detail_prompts_require_machine_readable_lists(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="القسم الرئيس", level=1),
                ExtractionItem(
                    title="ما أقسام المسألة؟",
                    level=2,
                    kind="end_question",
                ),
            ]
        )

        for prompt in prompts:
            self.assertIn('يبدأ حرفياً بـ "- "', prompt.prompt_text)
            self.assertIn('"1. "', prompt.prompt_text)

    def test_detail_prompts_preserve_lecturer_wording_and_order(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="القسم الرئيس", level=1),
                ExtractionItem(
                    title="ما خلاصة المسألة؟",
                    level=2,
                    kind="end_question",
                ),
            ]
        )

        for prompt in prompts:
            self.assertIn("لفظ الشارح", prompt.prompt_text)
            self.assertIn("ترتيب", prompt.prompt_text)
            self.assertIn("فصحن", prompt.prompt_text)
            self.assertIn("الجمل الانتقالية", prompt.prompt_text)
            self.assertNotIn("تصلح للمذاكرة", prompt.prompt_text)

    def test_detail_prompts_remove_repetition_without_losing_new_information(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="القسم الرئيس", level=1),
                ExtractionItem(
                    title="ما جواب المسألة؟",
                    level=2,
                    kind="end_question",
                ),
            ]
        )

        for prompt in prompts:
            self.assertIn("من باب الإعادة", prompt.prompt_text)
            self.assertIn("ليس لإضافة معلومة جديدة", prompt.prompt_text)
            self.assertIn("قيد أو مثال أو تفصيل", prompt.prompt_text)

    def test_output_name_advances_to_the_next_free_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "درس.docx").touch()
            (output_dir / "درس_v2.md").touch()

            with patch.object(settings, "OUTPUT_DIR", output_dir):
                output_name = next_output_name("درس")

        self.assertEqual("درس_v3", output_name)


if __name__ == "__main__":
    unittest.main()
