import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from app.config.settings import settings
from app.exporters.russian_course import (
    _normalize_summary_lines,
    canonical_category,
    get_prior_rule_names,
    load_state,
    merge_vocabulary,
    normalize_vocabulary_state,
    parse_vocabulary,
    prior_rule_names,
    remove_lecture_vocabulary,
    russian_key,
    _merge_text,
    update_cumulative_outputs,
)


VOCABULARY_SAMPLE = """
<vocabulary_item>
<category>التحيات</category>
<russian>Здра́вствуйте</russian>
<pronunciation>زْدرافستفويتي</pronunciation>
<translation>مرحباً بصيغة رسمية</translation>
<english>Hello formal</english>
</vocabulary_item>
<vocabulary_item>
<category>مقاطع صوتية</category>
<russian>ма</russian>
<pronunciation>ما</pronunciation>
<translation>مقطع صوتي للتدريب</translation>
<english>syllable</english>
</vocabulary_item>
"""


SUMMARY_SECTIONS = [
    (
        "الحروف الجديدة",
        "<subheading>الحرف А</subheading>\n"
        "<russian>А а</russian>\n"
        "<pronunciation>آ</pronunciation>\n"
        "<translation>حرف متحرك</translation>",
    ),
    (
        "القواعد والتطبيقات",
        "<subheading>الحروف المتحركة</subheading>\n"
        "تخرج من دون إغلاق مجرى الهواء.",
    ),
    (
        "الحوارات الروسية",
        "<speaker>A</speaker>\n"
        "<russian>Кто это?</russian>\n"
        "<pronunciation>كتو إيتا؟</pronunciation>\n"
        "<translation>من هذا؟</translation>",
    ),
    (
        "الخلاصة والواجب",
        "- مراجعة الحرف الجديد.\n- كتابة المثال مرة واحدة.",
    ),
]


class RussianCourseVocabularyTests(unittest.TestCase):
    def test_filter_handles_marked_drills_and_break_phrases_in_saved_state(self):
        state = {'vocabulary': [
            {'russian': 'переры́в 10 мину́т', 'arabic': 'استراحة'},
            {'russian': 'па́мба', 'arabic': 'مَقْطَعٌ تَدْرِيبِيٌّ مَرَّكَبٌ'},
            {'russian': 'на', 'arabic': 'مَقْطَعٌ صَوْتِيٌّ'},
            {'russian': 'пам', 'english': 'Practice word'},
            {'russian': 'Читайте', 'arabic': 'اقرؤوا'},
            {'russian': 'на', 'arabic': 'على', 'english': 'On'},
        ]}
        normalize_vocabulary_state(state)
        self.assertEqual(['Читайте', 'на'], [v['russian'] for v in state['vocabulary']])

    def test_meaning_merge_deduplicates_alternatives_not_parenthetical_slashes(self):
        self.assertEqual('شكراً / امتنان', _merge_text('شكراً', 'شُكْرًا / امتنان'))
        self.assertEqual("Please / You're welcome", _merge_text(
            "Please / You're welcome", "You're welcome / Please"))
        self.assertEqual('You (formal / plural)', _merge_text('', 'You (formal / plural)'))
        self.assertNotEqual(russian_key('и'), russian_key('й'))
        self.assertNotEqual(russian_key('все'), russian_key('всё'))
        self.assertEqual(russian_key('она́'), russian_key('она'))

    def test_normalize_state_merges_stressed_and_unstressed_duplicate_rows(self):
        state = {"vocabulary": [
            {"russian": "проверя́ем", "pronunciation": "پْرَاڤِيرْيَايِمْ",
             "pronunciation_reviewed": True, "arabic": "نتحقق", "english": "We check",
             "lectures": [2], "order": 1},
            {"russian": "Проверяем", "pronunciation": "پْرَڤِيرْيَايِمْ",
             "arabic": "نراجع", "english": "We verify", "lectures": [4], "order": 2},
        ]}
        normalize_vocabulary_state(state)
        self.assertEqual(1, len(state["vocabulary"]))
        self.assertEqual([2, 4], state["vocabulary"][0]["lectures"])
        self.assertEqual("پْرَاڤِيرْيَايِمْ", state["vocabulary"][0]["pronunciation"])

    def test_reviewed_pronunciation_survives_subsequent_lectures(self):
        state = {'vocabulary': [{'russian': 'Папа', 'pronunciation': 'پَاپَا',
                 'pronunciation_reviewed': True, 'arabic': 'أب', 'english': 'Dad',
                 'lectures': [1], 'order': 1}], 'next_order': 2}
        merge_vocabulary(state, [{'russian': 'па́па', 'pronunciation': 'بَابَا',
                         'arabic': 'والد', 'english': 'Father'}], 2)
        self.assertEqual('پَاپَا', state['vocabulary'][0]['pronunciation'])
        self.assertEqual([1, 2], state['vocabulary'][0]['lectures'])
        self.assertIn('Father', state['vocabulary'][0]['english'])

    def test_inline_summary_tags_are_split_for_word_styling(self):
        lines = _normalize_summary_lines(
            "<subheading>قاعدة</subheading> شرح مختصر "
            "<russian>Она</russian> <pronunciation>أنا</pronunciation>"
        )

        self.assertEqual(
            [
                "<subheading>قاعدة</subheading>",
                "شرح مختصر",
                "<russian>Она</russian>",
                "<pronunciation>أنا</pronunciation>",
            ],
            lines,
        )

    def test_parse_vocabulary_filters_sound_drills(self):
        entries = parse_vocabulary(VOCABULARY_SAMPLE)

        self.assertEqual(1, len(entries))
        self.assertEqual("Здра́вствуйте", entries[0]["russian"])
        self.assertEqual("التحيات والوداعات", entries[0]["category"])

    def test_parse_vocabulary_filters_break_and_praise_chatter(self):
        text = """
<vocabulary_item><category>الصف</category><russian>Перерыв</russian><pronunciation>بيريريف</pronunciation><translation>استراحة</translation><english>Break</english></vocabulary_item>
<vocabulary_item><category>الصف</category><russian>Всё правильно</russian><pronunciation>فسيو برافيلنا</pronunciation><translation>كل شيء صحيح</translation><english>Everything is correct</english></vocabulary_item>
<vocabulary_item><category>الصف</category><russian>Читайте</russian><pronunciation>تشيتايتي</pronunciation><translation>اقرؤوا</translation><english>Read</english></vocabulary_item>
"""

        entries = parse_vocabulary(text)

        self.assertEqual(["Читайте"], [entry["russian"] for entry in entries])

    def test_normalize_state_recategorizes_pronouns_and_people(self):
        state = {
            "vocabulary": [
                {
                    "category": "أخرى",
                    "russian": "Она",
                    "arabic": "هي",
                    "english": "She",
                },
                {
                    "category": "أخرى",
                    "russian": "Студент",
                    "arabic": "طالب",
                    "english": "Student",
                },
            ]
        }

        normalize_vocabulary_state(state)

        self.assertEqual(
            "الضمائر وأسماء الإشارة",
            state["vocabulary"][0]["category"],
        )
        self.assertEqual(
            "الأشخاص والمهن",
            state["vocabulary"][1]["category"],
        )

    def test_explicit_topic_beats_substring_in_arabic_meaning(self):
        state = {"vocabulary": [
            {"category": "الطقس والطبيعة", "russian": "Вьюга",
             "arabic": "عاصفة ثلجية", "english": "Blizzard"},
            {"category": "الأسئلة والأجوبة", "russian": "Где банк?",
             "arabic": "أين البنك؟", "english": "Where is the bank?"},
        ]}
        normalize_vocabulary_state(state)
        self.assertEqual(
            ["الطقس والطبيعة", "الأسئلة والأجوبة"],
            [item["category"] for item in state["vocabulary"]],
        )

    def test_merge_vocabulary_keeps_one_row_and_all_lecture_numbers(self):
        state = {
            "vocabulary": [],
            "next_order": 1,
        }
        entry = parse_vocabulary(VOCABULARY_SAMPLE)[0]

        merge_vocabulary(state, [entry], 1)
        merge_vocabulary(state, [entry], 2)

        self.assertEqual(1, len(state["vocabulary"]))
        self.assertEqual([1, 2], state["vocabulary"][0]["lectures"])

    def test_category_mapping_is_semantic_not_alphabetical(self):
        self.assertEqual(
            "الصف والتعليمات",
            canonical_category("أوامر الصف والتعليمات"),
        )
        self.assertEqual(
            "الطقس والطبيعة",
            canonical_category("الطقس"),
        )

    def test_adjective_and_color_categories_are_not_classroom_words(self):
        for label in ("الصفات المتضادة", "وصف الأشياء", "الأوصاف والألوان"):
            with self.subTest(label=label):
                self.assertEqual("الصفات", canonical_category(label))

    def test_places_word_is_not_misfiled_under_family_by_partial_match(self):
        # "أماكن" (places) starts with the same two letters as "أم" (mother),
        # which used to make a naive substring check route it to "العائلة".
        self.assertEqual(
            "الأماكن والمواصلات",
            canonical_category("أماكن"),
        )
        self.assertEqual(
            "الأماكن والمواصلات",
            canonical_category("الأماكن"),
        )

    def test_family_word_with_definite_article_still_matches(self):
        self.assertEqual("العائلة", canonical_category("الأم"))
        self.assertEqual("العائلة", canonical_category("أب"))
        self.assertEqual("العائلة", canonical_category("العائلة"))

    def test_letter_term_is_not_misfiled_as_hot_weather(self):
        self.assertEqual(
            "القواعد والمصطلحات",
            canonical_category("حرف كبير"),
        )


class RemoveLectureVocabularyTests(unittest.TestCase):
    def test_drops_a_word_that_belonged_only_to_this_lecture(self):
        state = {
            "vocabulary": [
                {"russian": "стол", "lectures": [1], "order": 1},
            ],
        }

        remove_lecture_vocabulary(state, 1)

        self.assertEqual([], state["vocabulary"])

    def test_keeps_a_word_shared_with_another_lecture_minus_this_one(self):
        state = {
            "vocabulary": [
                {"russian": "мама", "lectures": [1, 2], "order": 1},
            ],
        }

        remove_lecture_vocabulary(state, 1)

        self.assertEqual([2], state["vocabulary"][0]["lectures"])

    def test_leaves_other_lectures_untouched(self):
        state = {
            "vocabulary": [
                {"russian": "стол", "lectures": [2], "order": 1},
            ],
        }

        remove_lecture_vocabulary(state, 1)

        self.assertEqual([2], state["vocabulary"][0]["lectures"])


class RussianCourseCumulativeExportTests(unittest.TestCase):
    def test_update_creates_two_separate_cumulative_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                summary_path, vocabulary_path, lecture_number = (
                    update_cumulative_outputs(
                        "1الأولى.mp3",
                        SUMMARY_SECTIONS,
                        VOCABULARY_SAMPLE,
                    )
                )
                summary = Document(summary_path)
                vocabulary = Document(vocabulary_path)
                state = load_state()

            summary_text = "\n".join(
                paragraph.text for paragraph in summary.paragraphs
            )
            vocabulary_text = "\n".join(p.text for p in vocabulary.paragraphs) + "\n" + "\n".join(
                cell.text
                for table in vocabulary.tables
                for row in table.rows
                for cell in row.cells
            )

        self.assertEqual(1, lecture_number)
        self.assertTrue(summary_path.name.endswith("1-1.docx"))
        self.assertTrue(vocabulary_path.name.endswith("1-1 - مراجعة.docx"))
        self.assertEqual(
            "ملخص كورس اللغة الروسية المحاضرة الأولى",
            summary.paragraphs[0].text,
        )
        self.assertEqual(
            "جدول مفردات اللغة الروسية المحاضرة الأولى",
            vocabulary.paragraphs[0].text,
        )
        self.assertIn("المحاضرة الأولى", summary_text)
        self.assertIn("الحروف الجديدة", summary_text)
        self.assertIn("القواعد والتطبيقات", summary_text)
        self.assertNotIn("English meaning", summary_text)
        self.assertEqual(0, len(summary.tables))
        self.assertIn("Hello (formal)", vocabulary_text)
        self.assertIn("المحاضرات / المصدر", vocabulary_text)
        self.assertIn("здравствуйте", vocabulary_text.casefold().replace("\u0301", ""))
        self.assertEqual(1, len(state["vocabulary"]))
        self.assertEqual(
            ["الحروف المتحركة"],
            prior_rule_names(state),
        )

    def test_rerunning_same_lecture_replaces_it_without_duplicate_word(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                update_cumulative_outputs(
                    "1الأولى.mp3",
                    SUMMARY_SECTIONS,
                    VOCABULARY_SAMPLE,
                )
                update_cumulative_outputs(
                    "1الأولى.mp3",
                    SUMMARY_SECTIONS,
                    VOCABULARY_SAMPLE,
                )
                state = load_state()

        self.assertEqual(["1"], list(state["lectures"]))
        self.assertEqual(1, len(state["vocabulary"]))
        self.assertEqual([1], state["vocabulary"][0]["lectures"])

    def test_rerunning_a_lecture_drops_a_word_no_longer_extracted(self):
        first_vocabulary = VOCABULARY_SAMPLE
        second_vocabulary = """
<vocabulary_item>
<category>التحيات</category>
<russian>Пока</russian>
<pronunciation>باكا</pronunciation>
<translation>إلى اللقاء</translation>
<english>Bye</english>
</vocabulary_item>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                update_cumulative_outputs(
                    "1الأولى.mp3", SUMMARY_SECTIONS, first_vocabulary
                )
                update_cumulative_outputs(
                    "1الأولى.mp3", SUMMARY_SECTIONS, second_vocabulary
                )
                state = load_state()

        russian_words = {entry["russian"] for entry in state["vocabulary"]}
        self.assertEqual({"Пока"}, russian_words)

    def test_rerunning_a_lecture_keeps_another_lectures_word_untouched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                update_cumulative_outputs(
                    "1الأولى.mp3", SUMMARY_SECTIONS, VOCABULARY_SAMPLE
                )
                update_cumulative_outputs(
                    "2الثانية.mp3", SUMMARY_SECTIONS, VOCABULARY_SAMPLE
                )
                # Re-running lecture 1 must not disturb lecture 2's copy of
                # the same shared word.
                update_cumulative_outputs(
                    "1الأولى.mp3", SUMMARY_SECTIONS, VOCABULARY_SAMPLE
                )
                state = load_state()

        entry = next(
            item
            for item in state["vocabulary"]
            if item["russian"] == "Здра́вствуйте"
        )
        self.assertEqual([1, 2], entry["lectures"])

    def test_get_prior_rule_names_excludes_the_lecture_being_reprocessed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                update_cumulative_outputs(
                    "1الأولى.mp3", SUMMARY_SECTIONS, VOCABULARY_SAMPLE
                )

                # Re-processing lecture 1 must not treat its own just-saved
                # rules as "a prior lecture's" rules needing only a review.
                self.assertEqual(
                    [], get_prior_rule_names("1الأولى.mp3")
                )

                update_cumulative_outputs(
                    "2الثانية.mp3", SUMMARY_SECTIONS, VOCABULARY_SAMPLE
                )

                # A genuinely different lecture still sees lecture 1's rules.
                self.assertEqual(
                    ["الحروف المتحركة"],
                    get_prior_rule_names("3الثالثة.mp3"),
                )
                # Lecture 2 is excluded for its own reprocessing, but
                # lecture 1's rule (a different lecture) still applies.
                self.assertEqual(
                    ["الحروف المتحركة"],
                    get_prior_rule_names("2الثانية.mp3"),
                )


if __name__ == "__main__":
    unittest.main()
