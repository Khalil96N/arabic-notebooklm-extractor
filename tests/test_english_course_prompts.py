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
        self.assertIn("ملاحظات دراسية عربية مفصلة", section)
        self.assertIn("بين أقواس", section)
        self.assertIn("<equation>", section)
        self.assertIn("<logistics>", section)
        self.assertNotIn("<english>", section)
        self.assertIn("درجات الحرية (Degrees of Freedom)", section)
        self.assertIn("لا تنقل جمل الدكتور الإنجليزية", section)
        self.assertIn("لا تقصر المفردات على المصطلحات التقنية", section)
        self.assertIn("لا تختلق اقتباساً", section)
        self.assertIn("كل فكرة فرعية ومثال وخطوة ومقارنة ومعادلة", section)
        self.assertNotIn("بسم الله", section)
        self.assertNotIn("بما أن هذه الفقرة هي خاتمة المحاضرة", section)

    def test_english_outline_filters_noise_and_requests_scientific_review(self):
        prompt = build_outline_prompt("Robotics Fundamentals")

        self.assertIn("تجاهل التحية والتعريف الشخصي", prompt)
        self.assertIn("المعلومة التنظيمية التي يحتاج الطالب", prompt)
        self.assertIn("3-5 أسئلة مراجعة علمية", prompt)
        self.assertIn("لا تكتب الشرح أو إجابات الأسئلة الآن", prompt)
        self.assertIn("لا تنشئ ترقيمًا تسلسليًا للعناوين", prompt)
        self.assertIn("وفق أرقام المصدر", prompt)

    def test_english_section_avoids_added_examples_and_follow_up_questions(self):
        prompt = PromptGenerator.generate_prompts(
            [ExtractionItem(title="Kinematics", level=1)],
            "english",
        )[0].prompt_text

        self.assertIn("اعتمد أمثلة المحاضر فقط", prompt)
        self.assertIn("لا تضف أمثلة جديدة من عندك", prompt)
        self.assertIn("لا تُقحم مصطلحات أو أفكاراً غير واردة فيه", prompt)
        self.assertIn("لا تطرح أسئلة متابعة", prompt)

    def test_english_prompts_place_recap_before_review_questions(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="Kinematics", level=1),
                ExtractionItem(
                    title="ما العلاقة بين الحركة والمفاصل؟",
                    level=2,
                    kind="end_question",
                ),
            ],
            "english",
        )

        self.assertEqual(
            [
                "Kinematics",
                "خلاصة المحاضرة",
                "سؤال للمراجعة: ما العلاقة بين الحركة والمفاصل؟",
                "استخراج المعلومات التنظيمية",
            ],
            [prompt.heading for prompt in prompts],
        )
        self.assertIn("5-8 نقاط واضحة", prompts[1].prompt_text)
        self.assertIn("إجابة تعليمية عربية دقيقة", prompts[2].prompt_text)
        self.assertNotIn("<english>", prompts[2].prompt_text)
        self.assertEqual("logistics", prompts[3].output_kind)
        self.assertIn("المحاضرة الإنجليزية المحددة كاملة", prompts[3].prompt_text)
        self.assertIn(
            "اكتب فقط المعلومات الصريحة في المصدر",
            prompts[3].prompt_text,
        )
        self.assertIn("كتلة فارغة تماماً", prompts[3].prompt_text)

    def test_english_topic_headings_keep_source_numbers_without_renumbering(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="5. Dynamics", level=1),
                ExtractionItem(title="2. Kinematics", level=1),
            ],
            "english",
        )

        self.assertEqual(
            ["2. Kinematics", "5. Dynamics"],
            [prompt.heading for prompt in prompts[:2]],
        )

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
