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
    chunk_response_has_all_sections,
    missing_chunk_sections,
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

        self.assertIn("اعتمد المعلمة مرة واحدة", section)
        self.assertIn("احذف تكرار الطلاب", section)
        self.assertIn("أسماء الطلاب والإدارة والحضور ومشكلات الاتصال", section)

    def test_letters_keep_only_small_useful_pronunciation_sample(self):
        _heading, prompt_text, _kind = build_chunk_prompt("")

        letters = prompt_text.split("<letters_section>")[1].split("</letters_section>")[0]
        self.assertIn("أمثلة نطق قليلة", letters)
        self.assertIn("بلا رسم أو سلاسل تدريب", letters)
        self.assertNotIn("<vocabulary_item>", letters)

    def test_prior_rules_are_passed_as_review_context(self):
        _heading, prompt_text, _kind = build_chunk_prompt(
            "", ["جنس الأسماء", "ضمائر الملكية"]
        )

        self.assertIn("جنس الأسماء", prompt_text)
        self.assertIn("ضمائر الملكية", prompt_text)
        self.assertIn("للمكرر اكتب مراجعة وأضف الجديد فقط", prompt_text)

    def test_review_context_is_bounded_and_keeps_recent_rules(self):
        names = [f"قاعدة قديمة رقم {i} " + "شرح طويل " * 20 for i in range(50)]
        names.append("التمييز الجديد بين المفرد والجمع في فعل الإعجاب (Мне нравится / Мне нравятся)")
        _, prompt, _ = build_chunk_prompt("", names)
        context = prompt.split("قواعد سابقة: ", 1)[1].split("</rules_section>", 1)[0]
        self.assertLessEqual(len(prompt), 1800)
        self.assertIn("التمييز الجديد بين المفرد والجمع في فعل الإعجاب", context)
        self.assertNotIn("قاعدة قديمة رقم 0 ", context)

    def test_full_chunk_leaves_room_for_response_id_with_long_boundaries(self):
        context = build_boundary_context("Начало " * 200, "Конец " * 200)
        _, prompt, _ = build_chunk_prompt(context, ["قاعدة طويلة " * 30] * 100)
        marker = "NBX-RETRY-1234567890"
        wrapped = (f"اكتب هوية الرد [[{marker}]] في أول سطر، ثم أجب عن الطلب التالي كاملاً:\n\n"
                   + prompt + f"\n\nالسطر الأول حرفيًا قبل أي وسم أو عنوان: [[{marker}]]")
        self.assertLessEqual(len(prompt), 1800)
        self.assertLess(len(wrapped), 2000)
        for tag in ("letters_section", "rules_section", "dialogues_section", "vocabulary_section"):
            self.assertIn(f"<{tag}>", prompt)
            self.assertIn(f"</{tag}>", prompt)

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
        self.assertIn("العبارة كاملة", vocabulary_section)
        self.assertIn("الكلمات ذات المعنى المستقل", vocabulary_section)

    def test_vocabulary_includes_useful_teacher_speech_beyond_lesson_text(self):
        _heading, prompt_text, _kind = build_chunk_prompt("")
        vocabulary_section = prompt_text.split("<vocabulary_section>")[1].split(
            "</vocabulary_section>"
        )[0]

        self.assertIn("من كلام المعلمة الروسي أثناء الشرح", vocabulary_section)
        self.assertIn("حتى إن لم تقرأها من النص", vocabulary_section)
        self.assertIn("استبعد الكلام الإداري", vocabulary_section)
        self.assertIn("تكرار الطلاب", vocabulary_section)

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


class MissingChunkSectionsTests(unittest.TestCase):
    def test_complete_response_has_no_missing_sections(self):
        response = (
            "<letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>"
            "<rules_section>لا توجد قاعدة جديدة في هذا الجزء.</rules_section>"
            "<dialogues_section>لا يوجد حوار تعليمي في هذا الجزء.</dialogues_section>"
            "<vocabulary_section></vocabulary_section>"
        )

        self.assertEqual([], missing_chunk_sections(response))
        self.assertTrue(chunk_response_has_all_sections(response))

    def test_a_dropped_section_tag_is_reported_as_missing(self):
        response = (
            "<letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>"
            "<dialogues_section>لا يوجد حوار تعليمي في هذا الجزء.</dialogues_section>"
            "<vocabulary_section></vocabulary_section>"
        )

        self.assertEqual(["rules_section"], missing_chunk_sections(response))
        self.assertFalse(chunk_response_has_all_sections(response))

    def test_closing_tag_before_opening_tag_is_still_malformed(self):
        response = (
            "</letters_section><letters_section>"
            "<rules_section>لا توجد قاعدة جديدة.</rules_section>"
            "<dialogues_section>لا يوجد حوار.</dialogues_section>"
            "<vocabulary_section></vocabulary_section>"
        )

        self.assertIn("letters_section", missing_chunk_sections(response))
        self.assertFalse(chunk_response_has_all_sections(response))

    def test_empty_response_is_missing_every_section(self):
        self.assertEqual(
            [
                "letters_section",
                "rules_section",
                "dialogues_section",
                "vocabulary_section",
            ],
            missing_chunk_sections(""),
        )


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
