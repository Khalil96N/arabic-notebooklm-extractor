import unittest

from app.models.schemas import ExtractionItem
from app.parser.extraction_plan import ExtractionPlanParser
from app.prompts.generator import PromptGenerator


class ExtractionPlanParserTests(unittest.TestCase):
    def test_explicit_markers_can_share_one_line(self):
        text = (
            "[[رئيسي: أولاً: القسم الأول]] "
            "[[رئيسي: ثانياً: القسم الثاني]] "
            "[[رئيسي: ثالثاً: القسم الثالث]]"
        )

        items = ExtractionPlanParser.parse_items(text)

        self.assertEqual(
            [
                "أولاً: القسم الأول",
                "ثانياً: القسم الثاني",
                "ثالثاً: القسم الثالث",
            ],
            [item.title for item in items],
        )

    def test_explicit_main_markers_take_priority(self):
        text = """
[[رئيسي: المقدمة]]
محتوى المقدمة، وفيه [[نص داخل الفقرة]] لا يمثل عنواناً.
**السؤال: ما المقصود؟**

[[رئيسي: الفصل الأول]]
محتوى الفصل.
"""

        items = ExtractionPlanParser.parse_items(text)

        self.assertEqual(
            ["أولاً: المقدمة", "ثانياً: الفصل الأول"],
            [item.title for item in items],
        )

    def test_legacy_detection_only_accepts_line_start_headings(self):
        text = """
[[المقدمة]]
ورد في الشرح [[مصطلح بين أقواس]] داخل السطر.
[[السؤال: ما الحكم؟]]
[[الفصل الأول]]
"""

        items = ExtractionPlanParser.parse_items(text)

        self.assertEqual(
            ["أولاً: المقدمة", "ثانياً: الفصل الأول"],
            [item.title for item in items],
        )

    def test_duplicate_titles_are_normalized(self):
        text = """
[[رئيسي: أولاً: أحكامُ الصلاة]]
[[رئيسي: ثانياً: أحكام الصلاة]]
"""

        items = ExtractionPlanParser.parse_items(text)

        self.assertEqual(
            ["أولاً: أحكامُ الصلاة"],
            [item.title for item in items],
        )

    def test_prompt_generator_skips_non_main_levels(self):
        items = [
            ExtractionItem(title="قسم رئيسي", level=1),
            ExtractionItem(title="عنوان فرعي", level=2),
        ]

        prompts = PromptGenerator.generate_prompts(items)

        self.assertEqual(["أولاً: قسم رئيسي"], [item.heading for item in prompts])
        self.assertIn("(أولاً: قسم رئيسي)", prompts[0].prompt_text)

    def test_main_heading_about_questions_stays_a_transcript_prompt(self):
        items = [
            ExtractionItem(
                title="حسن السؤال والاستشكال",
                level=1,
                kind="main",
            ),
        ]

        prompts = PromptGenerator.generate_prompts(items)

        self.assertEqual(1, len(prompts))
        self.assertIn("حسن السؤال والاستشكال", prompts[0].heading)
        self.assertNotIn("حصراً بصيغة سؤال", prompts[0].prompt_text)
        self.assertNotIn("سؤال وجواب", prompts[0].prompt_text)

    def test_end_questions_are_extracted_only_after_explanation_boundary(self):
        text = """
[[رئيسي: أحكام المسألة]]
[[سؤال ختامي: سؤال ورد أثناء الشرح ولا ينبغي فصله]]
محتوى الشرح.
[[نهاية الشرح]]
[[سؤال ختامي: ما حكم الحالة الأولى؟]]
الجواب الأول مع استطراداته.
[[سؤال ختامي: ما وجه الدليل؟]]
الجواب الثاني.
"""

        items = ExtractionPlanParser.parse_items(text)

        self.assertEqual(
            [
                ("أولاً: أحكام المسألة", "main"),
                ("ما حكم الحالة الأولى؟", "end_question"),
                ("ما وجه الدليل؟", "end_question"),
            ],
            [(item.title, item.kind) for item in items],
        )

    def test_each_end_question_gets_a_separate_complete_answer_prompt(self):
        items = [
            ExtractionItem(title="القسم الرئيس", level=1),
            ExtractionItem(
                title="ما حكم المسألة؟",
                level=2,
                kind="end_question",
            ),
            ExtractionItem(
                title="ما الدليل؟",
                level=2,
                kind="end_question",
            ),
        ]

        prompts = PromptGenerator.generate_prompts(items)

        self.assertEqual(
            [
                "أولاً: القسم الرئيس",
                "سؤال: ما حكم المسألة؟",
                "سؤال: ما الدليل؟",
            ],
            [item.heading for item in prompts],
        )
        self.assertIn("لا تختصر الجواب", prompts[1].prompt_text)
        self.assertIn("حتى بداية السؤال الختامي التالي", prompts[1].prompt_text)


if __name__ == "__main__":
    unittest.main()
