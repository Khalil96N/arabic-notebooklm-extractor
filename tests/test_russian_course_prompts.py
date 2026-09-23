import unittest
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import ExtractionItem
from app.prompts.generator import PromptGenerator
from app.prompts.profiles import get_prompt_profile, validate_content_type
from app.prompts.russian_course_templates import (
    build_boundary_context,
    build_chunk_prompt,
    build_outline_prompt,
    build_recap_prompt,
    split_chunk_response,
)
from app.services.notebooklm import NotebookLMService


class RussianCoursePromptTests(unittest.TestCase):
    def test_outline_targets_the_selected_russian_lesson(self):
        prompt = build_outline_prompt("ПОД-1541.mp3")

        self.assertIn("ПОД-1541.mp3", prompt)
        self.assertIn("درس اللغة الروسية المحدد فقط", prompt)

    def test_boundary_context_preserves_cyrillic_phrases(self):
        context = build_boundary_context("Буква А", "Следующая буква")

        self.assertIn("Буква А", context)
        self.assertIn("Следующая буква", context)

    def test_boundary_context_is_empty_without_hints(self):
        self.assertEqual("", build_boundary_context(None, None))

    def test_russian_outline_requests_chronological_chunks_covering_the_whole_lesson(
        self,
    ):
        prompt = build_outline_prompt("ПОД-154Т.mp3")

        self.assertIn("لا تنشئ أقساماً مستقلة", prompt)
        self.assertIn("قراءة كل طالب", prompt)
        self.assertIn("[[بداية:", prompt)
        self.assertIn("[[نهاية:", prompt)
        self.assertIn("استمر حتى نهاية الدرس", prompt)

    def test_russian_profile_runs_one_combined_call_per_chunk_plus_one_recap(
        self,
    ):
        items = [
            ExtractionItem(
                title="أولاً: الحروف А و О",
                level=1,
                start_hint="Здравствуйте",
                end_hint="Мы читаем букву А",
            ),
            ExtractionItem(
                title="ثانياً: الحرف М",
                level=1,
                start_hint="Теперь буква М",
                end_hint="До свидания",
            ),
        ]

        prompts = PromptGenerator.generate_prompts(items, "russian")

        # One combined call per chunk (not four), plus a single recap call.
        self.assertEqual(3, len(prompts))
        self.assertEqual(
            ["combined", "combined", "summary"],
            [prompt.output_kind for prompt in prompts],
        )
        self.assertEqual("الخلاصة والواجب", prompts[-1].heading)

        # Every combined call requests all four buckets in one prompt.
        for chunk_prompt in prompts[:2]:
            self.assertIn("<letters_section>", chunk_prompt.prompt_text)
            self.assertIn("<rules_section>", chunk_prompt.prompt_text)
            self.assertIn("<dialogues_section>", chunk_prompt.prompt_text)
            self.assertIn("<vocabulary_section>", chunk_prompt.prompt_text)

        # Every per-chunk call must stay scoped to its own boundary only.
        self.assertIn("Здравствуйте", prompts[0].prompt_text)
        self.assertIn("Мы читаем букву А", prompts[0].prompt_text)
        self.assertNotIn("Теперь буква М", prompts[0].prompt_text)

        self.assertIn("Теперь буква М", prompts[1].prompt_text)
        self.assertIn("До свидания", prompts[1].prompt_text)
        self.assertNotIn("Здравствуйте", prompts[1].prompt_text)

        # The single recap call is scoped to the LAST chunk, not the first.
        recap = prompts[-1]
        self.assertIn("Теперь буква М", recap.prompt_text)
        self.assertIn("До свидания", recap.prompt_text)
        self.assertNotIn("Здравствуйте", recap.prompt_text)

    def test_russian_profile_excludes_repeated_student_drills(self):
        prompts = PromptGenerator.generate_prompts(
            [ExtractionItem(title="تدريب قراءة الحروف", level=1)],
            "russian",
        )
        section = "\n".join(prompt.prompt_text for prompt in prompts)

        self.assertIn("اعتمد قراءة المعلمة مرة واحدة", section)
        self.assertIn("احذف إعادة الطلاب", section)
        self.assertIn("احذف الأسماء والمحاولات الفردية", section)
        self.assertIn("الحضور ومشكلات الاتصال", section)

    def test_letters_keep_only_small_useful_pronunciation_sample(self):
        _heading, prompt_text, _kind = build_chunk_prompt("")

        self.assertIn("بحد أقصى ستة مقاطع", prompt_text)
        self.assertIn("احذف السلاسل الطويلة", prompt_text)
        self.assertIn("لا تشرح خطوات رسم الحرف", prompt_text)
        self.assertIn("لا تنشئ قائمة مفردات هنا", prompt_text)

    def test_prior_rules_are_passed_as_review_context(self):
        _heading, prompt_text, _kind = build_chunk_prompt(
            "", ["جنس الأسماء", "ضمائر الملكية"]
        )

        self.assertIn("جنس الأسماء", prompt_text)
        self.assertIn("ضمائر الملكية", prompt_text)
        self.assertIn('سطرًا يبدأ بـ "مراجعة:"', prompt_text)

    def test_dialogue_and_vocabulary_sections_have_distinct_schemas(self):
        _heading, prompt_text, _kind = build_chunk_prompt("")

        dialogues_section = prompt_text.split("<dialogues_section>")[1].split(
            "</dialogues_section>"
        )[0]
        vocabulary_section = prompt_text.split("<vocabulary_section>")[1].split(
            "</vocabulary_section>"
        )[0]

        self.assertIn("<speaker>A</speaker>", dialogues_section)
        self.assertNotIn("<vocabulary_item>", dialogues_section)
        self.assertIn("<vocabulary_item>", vocabulary_section)
        self.assertIn("<category>", vocabulary_section)
        self.assertIn("<english>", vocabulary_section)

    def test_recap_prompt_is_scoped_to_the_boundary_it_is_given(self):
        heading, prompt_text, output_kind = build_recap_prompt(
            build_boundary_context("Урок окончен", "До завтра")
        )

        self.assertEqual("الخلاصة والواجب", heading)
        self.assertEqual("summary", output_kind)
        self.assertIn("Урок окончен", prompt_text)
        self.assertIn("До завтра", prompt_text)

    def test_content_type_validation_accepts_russian(self):
        self.assertEqual("russian", validate_content_type(" RUSSIAN "))
        self.assertIsNotNone(get_prompt_profile("russian"))


class SplitChunkResponseTests(unittest.TestCase):
    def test_splits_all_four_sections_by_their_tags(self):
        response = (
            "<letters_section>letters text</letters_section>\n"
            "<rules_section>rules text</rules_section>\n"
            "<dialogues_section>dialogues text</dialogues_section>\n"
            "<vocabulary_section>vocab text</vocabulary_section>"
        )

        parts = split_chunk_response(response)

        self.assertEqual("letters text", parts["letters"])
        self.assertEqual("rules text", parts["rules"])
        self.assertEqual("dialogues text", parts["dialogues"])
        self.assertEqual("vocab text", parts["vocabulary"])

    def test_missing_section_tag_resolves_to_empty_string(self):
        response = "<letters_section>only letters</letters_section>"

        parts = split_chunk_response(response)

        self.assertEqual("only letters", parts["letters"])
        self.assertEqual("", parts["rules"])
        self.assertEqual("", parts["dialogues"])
        self.assertEqual("", parts["vocabulary"])


class RussianCourseServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_uses_the_selected_russian_outline(self):
        page = MagicMock()
        page.url = "https://notebooklm.google.com/notebook/example"
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        service = NotebookLMService(context)
        service.page_client = MagicMock()
        service.page_client.open_configured_notebook = AsyncMock()
        service.page_client.send_prompt = AsyncMock()
        service.page_client.wait_for_response = AsyncMock(
            return_value="[[رئيسي: أولاً: الحرف А а]]"
        )

        await service.discover_extraction_plan(
            "Russian Language Fundamentals and Alphabet Basics",
            "ПОД-1541.mp3",
            content_type="russian",
        )

        sent_prompt = service.page_client.send_prompt.await_args.args[1]
        self.assertIn("درس اللغة الروسية المحدد فقط", sent_prompt)
        self.assertIn("ПОД-1541.mp3", sent_prompt)


if __name__ == "__main__":
    unittest.main()
