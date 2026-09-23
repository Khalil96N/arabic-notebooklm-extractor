import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.settings import settings
from app.models.schemas import ExtractionItem, PromptItem
from app.prompts.arabic_lecture_templates import build_outline_prompt
from app.prompts.generator import PromptGenerator
from app.utils.arabic import number_main_heading
from app.workflow import aggregate_russian_chunks, next_output_name


class WorkflowTests(unittest.TestCase):
    def test_outline_prompt_only_requests_the_extraction_plan(self):
        prompt = build_outline_prompt("المحاضرة", "الكتاب")

        self.assertIn("المحاضرة", prompt)
        self.assertIn("الكتاب", prompt)
        self.assertIn("[[رئيسي: أولاً:", prompt)
        self.assertIn("[[بداية:", prompt)
        self.assertIn("[[نهاية:", prompt)
        self.assertIn("[[سؤال ختامي: نص السؤال]]", prompt)
        self.assertIn("لا تكتب التفريغ الكامل", prompt)
        self.assertIn("لا تكتب جواب السؤال أو محتوى أي قسم", prompt)

    def test_outline_prompt_scales_heading_count_for_long_lectures(self):
        prompt = build_outline_prompt("محاضرة طويلة")

        self.assertIn("ساعة ونصفاً (90 دقيقة)", prompt)
        self.assertIn("8-12 دقيقة", prompt)
        self.assertIn("6-8 دقائق", prompt)
        self.assertIn("9-14 عنواناً", prompt)
        self.assertIn("ساعتين (120 دقيقة)", prompt)
        self.assertIn("14-20 عنواناً", prompt)

    def test_outline_prompt_source_context_keeps_instruction_numbering(self):
        prompt = build_outline_prompt("المحاضرة", "الكتاب")

        self.assertIn("10- المصدر الأساسي المطلوب تحليله", prompt)

    def test_outline_prompt_keeps_in_lecture_questions_inside_topics(self):
        prompt = build_outline_prompt("محاضرة")

        self.assertIn("أسئلة التذكير", prompt)
        self.assertIn("ضمن الموضوع الرئيسي الأقرب", prompt)
        self.assertIn('لا تجعل عنواناً رئيسياً يبدأ بـ "سؤال:"', prompt)

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
            self.assertIn("المتن أولاً", prompt.prompt_text)
            self.assertIn(
                "شرح الشارح بعده مباشرة في فقرة مستقلة خارج الوسم",
                prompt.prompt_text,
            )
            self.assertIn("فقرة مستقلة", prompt.prompt_text)
            self.assertIn("لا تخلط المتن والشرح", prompt.prompt_text)
            self.assertIn("لا تترك المتن المقروء بلا وسم", prompt.prompt_text)

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
            self.assertIn("لا تكتف بخلاصة", prompt.prompt_text)
            self.assertIn("لا تنه", prompt.prompt_text)
            self.assertNotIn("تصلح للمذاكرة", prompt.prompt_text)

    def test_section_prompt_summarizes_in_lecture_dialogue_questions(self):
        prompts = PromptGenerator.generate_prompts(
            [ExtractionItem(title="تعريف الحدث", level=1)]
        )
        prompt = prompts[0].prompt_text

        self.assertIn("سؤال تذكيري", prompt)
        self.assertIn("فلا تنقل الحوار كاملاً", prompt)
        self.assertIn("الخلاصة العلمية مباشرة", prompt)
        self.assertIn("الحدث في الفقه يطلق على ثلاثة أمور", prompt)
        self.assertIn("هذا خاص بالحوار التعليمي العارض فقط", prompt)

    def test_detail_prompts_require_direct_lecturer_voice(self):
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
            self.assertTrue(
                "لا تكتب" in prompt.prompt_text
                or "ولا تحك عنه" in prompt.prompt_text
            )
            self.assertIn("قال الشارح", prompt.prompt_text)
            self.assertIn("يبين الشارح", prompt.prompt_text)
            self.assertIn("مباشرة", prompt.prompt_text)

    def test_first_detail_prompt_starts_from_lecturer_intro(self):
        prompts = PromptGenerator.generate_prompts(
            [
                ExtractionItem(title="القسم الأول", level=1),
                ExtractionItem(title="القسم الثاني", level=1),
            ]
        )

        self.assertIn("العنوان الأول", prompts[0].prompt_text)
        self.assertIn("مقدمة الشارح", prompts[0].prompt_text)
        self.assertIn("بسم الله", prompts[0].prompt_text)
        self.assertIn("الحمد لله", prompts[0].prompt_text)
        self.assertNotIn("مقدمة الشارح", prompts[1].prompt_text)
        self.assertNotIn("بسم الله", prompts[1].prompt_text)

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

    def test_number_main_heading_removes_repeated_ordinal_prefixes(self):
        self.assertEqual(
            "الحادي عشر: خصوصية نوم النبي وحكم نوم الصحابة",
            number_main_heading(
                "الحادي عشر: حادي عشر: خصوصية نوم النبي وحكم نوم الصحابة",
                11,
            ),
        )

    def _combined_chunk_text(self, tag: str) -> str:
        return (
            "<letters_section>"
            f"<subheading>الحروف الجديدة</subheading> letters {tag}"
            "</letters_section>"
            "<rules_section>"
            f"<subheading>قاعدة {tag}</subheading> rules {tag}"
            "</rules_section>"
            "<dialogues_section>"
            f"<subheading>الحوارات الروسية</subheading> dialogues {tag}"
            "</dialogues_section>"
            "<vocabulary_section>"
            f"<vocabulary_item><russian>слово{tag}</russian></vocabulary_item>"
            "</vocabulary_section>"
        )

    def test_aggregate_russian_chunks_splits_combined_calls_and_joins_in_order(
        self,
    ):
        prompts = [
            PromptItem(heading="قسم من الدرس", prompt_text="p1", output_kind="combined"),
            PromptItem(heading="قسم من الدرس", prompt_text="p2", output_kind="combined"),
            PromptItem(heading="الخلاصة والواجب", prompt_text="p3", output_kind="summary"),
        ]
        sections = [
            ("قسم من الدرس", self._combined_chunk_text("chunk1")),
            ("قسم من الدرس", self._combined_chunk_text("chunk2")),
            ("الخلاصة والواجب", "<subheading>الخلاصة والواجب</subheading> recap text"),
        ]

        summary_sections, vocabulary_text = aggregate_russian_chunks(
            prompts, sections
        )
        headings = [heading for heading, _text in summary_sections]

        self.assertEqual(
            ["الحروف الجديدة", "القواعد والتطبيقات", "الحوارات الروسية", "الخلاصة والواجب"],
            headings,
        )
        letters_text = dict(summary_sections)["الحروف الجديدة"]
        self.assertIn("letters chunk1", letters_text)
        self.assertIn("letters chunk2", letters_text)
        rules_text = dict(summary_sections)["القواعد والتطبيقات"]
        self.assertIn("rules chunk1", rules_text)
        self.assertIn("rules chunk2", rules_text)
        self.assertIn("recap text", dict(summary_sections)["الخلاصة والواجب"])
        self.assertIn("словоchunk1", vocabulary_text)
        self.assertIn("словоchunk2", vocabulary_text)

    def test_aggregate_russian_chunks_merges_a_rule_split_across_two_chunks(
        self,
    ):
        prompts = [
            PromptItem(heading="قسم من الدرس", prompt_text="p1", output_kind="combined"),
            PromptItem(heading="قسم من الدرس", prompt_text="p2", output_kind="combined"),
        ]
        sections = [
            (
                "قسم من الدرس",
                "<letters_section></letters_section>"
                "<rules_section>"
                "<subheading>جنس الأسماء</subheading> "
                "<russian>стол</russian> <translation>طاولة</translation>"
                "</rules_section>"
                "<dialogues_section></dialogues_section>"
                "<vocabulary_section></vocabulary_section>",
            ),
            (
                "قسم من الدرس",
                "<letters_section></letters_section>"
                "<rules_section>"
                "<subheading>جنس الأسماء</subheading> "
                "<russian>книга</russian> <translation>كتاب</translation>"
                "</rules_section>"
                "<dialogues_section></dialogues_section>"
                "<vocabulary_section></vocabulary_section>",
            ),
        ]

        summary_sections, _vocabulary_text = aggregate_russian_chunks(
            prompts, sections
        )
        rules_text = dict(summary_sections)["القواعد والتطبيقات"]

        self.assertEqual(1, rules_text.count("جنس الأسماء"))
        self.assertIn("стол", rules_text)
        self.assertIn("книга", rules_text)

    def test_aggregate_russian_chunks_skips_empty_buckets(self):
        prompts = [
            PromptItem(heading="قسم من الدرس", prompt_text="p1", output_kind="combined"),
        ]
        sections = [
            (
                "قسم من الدرس",
                "<letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>"
                "<rules_section></rules_section>"
                "<dialogues_section></dialogues_section>"
                "<vocabulary_section></vocabulary_section>",
            ),
        ]

        summary_sections, vocabulary_text = aggregate_russian_chunks(
            prompts, sections
        )

        headings = [heading for heading, _text in summary_sections]
        self.assertEqual(["الحروف الجديدة"], headings)
        self.assertEqual("", vocabulary_text)

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
