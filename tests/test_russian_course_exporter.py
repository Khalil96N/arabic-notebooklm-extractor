import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from app.config.settings import settings
from app.exporters.russian_course import (
    canonical_category,
    load_state,
    merge_vocabulary,
    parse_vocabulary,
    prior_rule_names,
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
    def test_parse_vocabulary_filters_sound_drills(self):
        entries = parse_vocabulary(VOCABULARY_SAMPLE)

        self.assertEqual(1, len(entries))
        self.assertEqual("Здра́вствуйте", entries[0]["russian"])
        self.assertEqual("التحيات والوداعات", entries[0]["category"])

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
            vocabulary_text = "\n".join(
                cell.text
                for table in vocabulary.tables
                for row in table.rows
                for cell in row.cells
            )

        self.assertEqual(1, lecture_number)
        self.assertTrue(summary_path.name.endswith("1-1.docx"))
        self.assertTrue(vocabulary_path.name.endswith("1-1.docx"))
        self.assertIn("المحاضرة الأولى", summary_text)
        self.assertIn("الحروف الجديدة", summary_text)
        self.assertIn("القواعد والتطبيقات", summary_text)
        self.assertNotIn("English meaning", summary_text)
        self.assertEqual(0, len(summary.tables))
        self.assertIn("English meaning", vocabulary_text)
        self.assertIn("Здра́вствуйте", vocabulary_text)
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


if __name__ == "__main__":
    unittest.main()
