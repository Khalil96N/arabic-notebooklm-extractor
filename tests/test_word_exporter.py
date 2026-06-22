import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from app.config.settings import settings
from app.exporters.file import FileExporter


class WordExporterTests(unittest.TestCase):
    def test_arabic_section_ordinals(self):
        self.assertEqual("أولاً", FileExporter.arabic_ordinal(1))
        self.assertEqual("ثانياً", FileExporter.arabic_ordinal(2))
        self.assertEqual("الحادي عشر", FileExporter.arabic_ordinal(11))
        self.assertEqual("الحادي والعشرون", FileExporter.arabic_ordinal(21))

    def test_word_titles_are_numbered_above_their_paragraphs(self):
        sections = [
            ("أولاً: العنوان الأول", "هذه هي الفقرة الأولى."),
            ("ثانياً: العنوان الثاني", "هذه هي الفقرة الثانية."),
            ("سؤال: ما حكم المسألة؟", "س: ما حكم المسألة؟\nج: الجواب كاملاً."),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with (
                patch.object(settings, "OUTPUT_DIR", output_dir),
                patch.object(
                    FileExporter,
                    "get_current_dates",
                    return_value=("الأربعاء", "24 ذو الحجة 1447هـ", "2026-06-10"),
                ),
            ):
                FileExporter.save_word_document(sections, "اختبار الترقيم")

            document = Document(output_dir / "اختبار الترقيم.docx")
            header_cells = [
                cell.text for cell in document.tables[0].rows[0].cells
            ]
            paragraph_texts = [
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ]
            heading_styles = [
                paragraph.style.name
                for paragraph in document.paragraphs
                if paragraph.text.strip()
                and paragraph.runs
                and all(run.bold is True for run in paragraph.runs if run.text.strip())
                and any(run.font.size and run.font.size.pt == 16 for run in paragraph.runs)
            ]

        self.assertEqual(
            [
                "الأربعاء",
                "24 ذو الحجة 1447هـ",
                "2026-06-10",
                "اختبار الترقيم",
            ],
            header_cells,
        )
        self.assertEqual(
            [
                "أولاً: العنوان الأول",
                "هذه هي الفقرة الأولى.",
                "ثانياً: العنوان الثاني",
                "هذه هي الفقرة الثانية.",
                "السؤال الأول: ما حكم المسألة؟",
                "س: ما حكم المسألة؟",
                "ج: الجواب كاملاً.",
            ],
            paragraph_texts,
        )
        self.assertEqual(["Heading 1", "Heading 1", "Heading 1"], heading_styles)

    def test_markdown_heading_is_moved_to_a_new_line(self):
        text = "نهاية الفقرة السابقة. ## خامساً: عنوان الفقرة\n\nالمحتوى."

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_final_transcript(text, "اختبار")

            saved_text = (output_dir / "اختبار.md").read_text(
                encoding="utf-8"
            )

        self.assertIn(
            "نهاية الفقرة السابقة.\n\n## خامساً: عنوان الفقرة",
            saved_text,
        )

    def test_word_uses_real_list_styles_for_common_list_markers(self):
        sections = [
            (
                "عنوان القائمة",
                "- العنصر الأول\n"
                "• العنصر الثاني\n"
                "1. المرحلة الأولى\n"
                "2) المرحلة الثانية",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار القوائم")

            document = Document(output_dir / "اختبار القوائم.docx")
            list_paragraphs = {
                paragraph.text: paragraph.style.name
                for paragraph in document.paragraphs
                if paragraph.text.startswith(("العنصر", "المرحلة"))
            }

        self.assertEqual(
            {
                "العنصر الأول": "List Bullet",
                "العنصر الثاني": "List Bullet",
                "المرحلة الأولى": "List Number",
                "المرحلة الثانية": "List Number",
            },
            list_paragraphs,
        )

    def test_word_infers_bullets_after_a_clear_list_introduction(self):
        sections = [
            (
                "عنوان القائمة",
                "من خصائص الكتاب، منها:\n"
                "دقة الترتيب.\n"
                "سهولة التناول.\n"
                "وقد انتهت القائمة.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار الاستنتاج")

            document = Document(output_dir / "اختبار الاستنتاج.docx")
            list_paragraphs = [
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.style.name == "List Bullet"
            ]

        self.assertEqual(
            ["دقة الترتيب.", "سهولة التناول."],
            list_paragraphs,
        )


if __name__ == "__main__":
    unittest.main()
