import tempfile
import unittest
import zipfile
import re
from pathlib import Path
from unittest.mock import patch

from docx import Document
from docx.shared import RGBColor

from app.config.settings import settings
from app.exporters.file import FileExporter


class WordExporterTests(unittest.TestCase):
    def test_english_notes_keep_parenthesized_terms_and_times_ltr_in_arabic(self):
        from docx.oxml.ns import qn

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(settings, "OUTPUT_DIR", Path(directory)):
                FileExporter.save_word_document(
                    [("مراجعة", "درجات الحرية (Degrees of Freedom) والموعد 14:00–16:00.\n"
                      "<equation>M = d × (n − 1 − g) + ∑_(i=1)^g f_i</equation>\n"
                      "حيث <equation>f_i</equation> درجة حرية المفصل.")],
                    "mixed_notes", number_main_headings=False,
                )
            document = Document(Path(directory) / "mixed_notes.docx")
            paragraph = next(p for p in document.paragraphs if "درجات الحرية" in p.text)
            self.assertEqual("1", paragraph._p.pPr.find(qn("w:bidi")).get(qn("w:val")))
            for token in ["(Degrees\u00a0of\u00a0Freedom)", "14:00–16:00"]:
                run = next(r for r in paragraph.runs if r.text.strip("\u200e") == token)
                self.assertEqual("0", run._r.rPr.find(qn("w:rtl")).get(qn("w:val")))
                self.assertEqual("\u200e" + token + "\u200e", run.text)
            xml = document._element.xml
            self.assertIn("<m:sSub>", xml)
            self.assertNotIn("f_i", xml)

    def test_companion_passages_keep_english_then_arabic_and_native_equations(self):
        from docx.oxml.ns import qn

        text = (
            "<english>\nThe system has one degree of freedom.\n</english>\n"
            "المعنى: يمتلك النظام درجة حرية واحدة.\n"
            "الشرح: يكفي متغير مستقل واحد لوصف حركته.\n"
            "كلمات تساعدك: <term>independent</term> = مستقل.\n"
            "<equation>M = 1</equation>\n"
            "<english>\nNow compare two systems.\n</english>\n"
            "المعنى: قارن الآن بين نظامين."
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(settings, "OUTPUT_DIR", Path(directory)):
                FileExporter.save_word_document(
                    [("Degrees of Freedom", text)], "companion", number_main_headings=False
                )
            doc = Document(Path(directory) / "companion.docx")
        paragraphs = [p for p in doc.paragraphs if p.text.strip()]
        english = next(p for p in paragraphs if p.text.startswith("The system"))
        meaning = next(p for p in paragraphs if p.text.startswith("المعنى:"))
        explanation = next(p for p in paragraphs if p.text.startswith("الشرح:"))
        self.assertLess(paragraphs.index(english), paragraphs.index(meaning))
        self.assertLess(paragraphs.index(meaning), paragraphs.index(explanation))
        self.assertEqual("0", english._p.pPr.find(qn("w:bidi")).get(qn("w:val")))
        self.assertEqual("1", meaning._p.pPr.find(qn("w:bidi")).get(qn("w:val")))
        self.assertEqual("1", explanation._p.pPr.find(qn("w:bidi")).get(qn("w:val")))
        self.assertTrue(english.paragraph_format.keep_with_next)
        self.assertTrue(doc.element.xpath(".//m:oMath"))
        self.assertNotIn("<english>", "\n".join(p.text for p in paragraphs))

    def test_unclosed_highlight_does_not_color_following_paragraphs(self):
        sections = [
            (
                "Heading",
                "Important divisions: <highlight>\n"
                "Lecturer explanation.\n"
                "</highlight>\n"
                "Lecturer continuation.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "highlight leak")

            document = Document(output_dir / "highlight leak.docx")
            explanation = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text == "Lecturer explanation."
            )
            continuation = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text == "Lecturer continuation."
            )

        self.assertIsNone(explanation.runs[0].font.color.rgb)
        self.assertIsNone(explanation.runs[0].bold)
        self.assertIsNone(continuation.runs[0].font.color.rgb)
        self.assertIsNone(continuation.runs[0].bold)

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

    def test_word_titles_can_preserve_source_order_without_added_ordinals(self):
        sections = [
            ("7. Mobility", "شرح القدرة الحركية."),
            ("2. Degrees of Freedom", "شرح درجات الحرية."),
            ("سؤال للمراجعة: ما الفرق؟", "الإجابة."),
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
                FileExporter.save_word_document(
                    sections,
                    "اختبار بلا ترقيم تلقائي",
                    number_main_headings=False,
                    document_title="عنوان المحاضرة من المصدر",
                )

            document = Document(output_dir / "اختبار بلا ترقيم تلقائي.docx")
            headings = [
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.style.name == "Heading 1"
            ]

        self.assertEqual(
            [
                "7. Mobility",
                "2. Degrees of Freedom",
                "سؤال للمراجعة: ما الفرق؟",
            ],
            headings,
        )
        self.assertEqual(
            "عنوان المحاضرة من المصدر",
            document.tables[0].rows[0].cells[3].text,
        )
        first_heading = next(
            paragraph
            for paragraph in document.paragraphs
            if paragraph.style.name == "Heading 1" and paragraph.runs
        )
        self.assertEqual(
            RGBColor(0, 0, 0),
            first_heading.runs[0].font.color.rgb,
        )

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

    def test_word_distinguishes_matn_before_following_explanation(self):
        sections = [
            (
                "عنوان المتن",
                "<matn>قول صاحب المتن.</matn> هذا شرح الشارح بعد المتن.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار المتن")

            document = Document(output_dir / "اختبار المتن.docx")
            paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if "قول صاحب المتن" in paragraph.text
            )
            matn_run = next(
                run for run in paragraph.runs if run.text == "قول صاحب المتن."
            )
            explanation_run = next(
                run
                for run in paragraph.runs
                if "هذا شرح الشارح بعد المتن" in run.text
            )

        self.assertEqual(
            "[قول صاحب المتن.] هذا شرح الشارح بعد المتن.",
            paragraph.text,
        )
        self.assertTrue(matn_run.bold)
        self.assertEqual("800080", str(matn_run.font.color.rgb))
        self.assertIsNone(explanation_run.bold)
        self.assertIsNone(explanation_run.font.color.rgb)

    def test_word_distinguishes_inline_subheadings(self):
        sections = [
            (
                "عنوان فرعي",
                "<subheading>حرب المرجعيات وضرب الإجماع</subheading> "
                "فإن هذه السيرورة الثقافية تحيد سلطان المؤسسات الدينية.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار الفرعي")

            document = Document(output_dir / "اختبار الفرعي.docx")
            paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if "حرب المرجعيات" in paragraph.text
            )
            subheading_run = next(
                run
                for run in paragraph.runs
                if "حرب المرجعيات وضرب الإجماع" in run.text
            )
            body_run = next(
                run
                for run in paragraph.runs
                if "السيرورة الثقافية" in run.text
            )

        self.assertEqual(
            "حرب المرجعيات وضرب الإجماع "
            "فإن هذه السيرورة الثقافية تحيد سلطان المؤسسات الدينية.",
            paragraph.text,
        )
        self.assertTrue(subheading_run.bold)
        self.assertEqual("C00000", str(subheading_run.font.color.rgb))
        self.assertIsNone(body_run.bold)
        self.assertIsNone(body_run.font.color.rgb)

    def test_word_keeps_standalone_inline_subheading_with_next_paragraph(self):
        sections = [
            (
                "عنوان فرعي",
                "<subheading>شرح المحاضرة المنظّم</subheading>\n"
                "تبدأ المعلمة بشرح الحروف الروسية.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار العنوان")

            document = Document(output_dir / "اختبار العنوان.docx")
            subheading = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text == "شرح المحاضرة المنظّم"
            )

        self.assertTrue(subheading.paragraph_format.keep_with_next)

    def test_word_exports_tagged_equations_as_native_office_math(self):
        sections = [
            (
                "المعادلات",
                "قبل المعادلة.\n"
                "<equation>z = w_1 x_1 + w_2 x_2 + b</equation>\n"
                "شرح الرموز بعد المعادلة.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار المعادلات")

            docx_path = output_dir / "اختبار المعادلات.docx"
            with zipfile.ZipFile(docx_path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("<m:oMathPara>", document_xml)
        self.assertRegex(document_xml, r"<m:oMath(?:\s|>)")
        self.assertIn("<m:sSub>", document_xml)
        self.assertNotIn("w_1", document_xml)
        self.assertNotIn("x_1", document_xml)
        self.assertNotIn("&lt;equation&gt;", document_xml)

    def test_word_formats_english_transcript_left_to_right(self):
        sections = [
            (
                "النص الإنجليزي",
                "<english>\n"
                "The decision boundary separates the two classes.\n"
                "</english>\n"
                "وهذا هو الشرح العربي.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار الإنجليزي")

            document = Document(output_dir / "اختبار الإنجليزي.docx")
            english_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if "decision boundary" in paragraph.text
            )
            english_run = english_paragraph.runs[0]
            arabic_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text.endswith(".")
                and "decision boundary" not in paragraph.text
            )
            docx_path = next(output_dir.glob("*.docx"))
            with zipfile.ZipFile(docx_path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertEqual(0, english_paragraph.alignment)
        self.assertEqual("Aptos", english_run.font.name)
        self.assertEqual(13, english_run.font.size.pt)
        self.assertEqual(2, arabic_paragraph.alignment)
        self.assertIn('<w:bidi w:val="0"', document_xml)
        self.assertIn('<w:bidi w:val="1"', document_xml)

    def test_word_formats_russian_pronunciation_and_translation_blocks(self):
        sections = [
            (
                "الحرف А а",
                "<russian>А а — ма́ма</russian>\n"
                "<pronunciation>اللفظ بالعربية: آ/أَ — ماما</pronunciation>\n"
                "<translation>المعنى بالعربية: أُمّ</translation>",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار الروسي")

            document = Document(output_dir / "اختبار الروسي.docx")
            russian_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if "ма́ма" in paragraph.text
            )
            pronunciation_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text.startswith("اللفظ بالعربية")
            )
            translation_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if paragraph.text.startswith("المعنى بالعربية")
            )

        self.assertEqual(0, russian_paragraph.alignment)
        self.assertTrue(russian_paragraph.paragraph_format.keep_with_next)
        self.assertEqual(15, russian_paragraph.runs[0].font.size.pt)
        self.assertTrue(russian_paragraph.runs[0].bold)
        self.assertEqual("7030A0", str(russian_paragraph.runs[0].font.color.rgb))
        self.assertEqual(2, pronunciation_paragraph.alignment)
        self.assertTrue(pronunciation_paragraph.paragraph_format.keep_with_next)
        self.assertEqual("008060", str(pronunciation_paragraph.runs[0].font.color.rgb))
        self.assertEqual(2, translation_paragraph.alignment)
        self.assertIsNone(translation_paragraph.paragraph_format.keep_with_next)
        self.assertEqual("1F4E79", str(translation_paragraph.runs[0].font.color.rgb))

    def test_word_keeps_prefixed_russian_card_together(self):
        sections = [
            (
                "Section",
                "Student: <russian>Russian</russian>\n"
                "<pronunciation>Pronunciation</pronunciation>\n"
                "<translation>Translation</translation>",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "russian_keep_next")

            document = Document(output_dir / "russian_keep_next.docx")
            source_paragraph = next(
                paragraph
                for paragraph in document.paragraphs
                if "Student: Russian" in paragraph.text
            )

        self.assertTrue(source_paragraph.paragraph_format.keep_with_next)

    def test_word_separates_collapsed_english_and_equation_blocks(self):
        sections = [
            (
                "التنسيق المدمج",
                "<subheading>النص الإنجليزي للشارح</subheading> "
                "<english>Raw English transcript.</english> "
                "<subheading>الشرح والإضافات بالعربية</subheading> "
                "شرح عربي: - <equation>y = w_1 x_1 + b</equation> "
                "ثم يتابع الشرح، والمتغير (<equation>x_1</equation>): "
                "هو الإدخال، والحالة الأخرى "
                "<equation>w x + b < 0</equation>.",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "اختبار الدمج")

            docx_path = output_dir / "اختبار الدمج.docx"
            document = Document(docx_path)
            paragraphs = [
                paragraph for paragraph in document.paragraphs if paragraph.text
            ]
            english_paragraph = next(
                paragraph
                for paragraph in paragraphs
                if "Raw English transcript" in paragraph.text
            )
            with zipfile.ZipFile(docx_path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertEqual("Raw English transcript.", english_paragraph.text)
        self.assertEqual(0, english_paragraph.alignment)
        self.assertEqual(
            3,
            len(re.findall(r"<m:oMath(?:\s|>)", document_xml)),
        )
        self.assertIn("<m:sSub>", document_xml)
        self.assertNotIn("y = w_1 x_1 + b", document_xml)
        self.assertNotIn("&lt;equation&gt;", document_xml)


    def test_word_equations_do_not_leave_visible_unicode_math_underscores(self):
        sections = [
            (
                "Equations",
                "<equation>w1_new = w1 - η × x1</equation>\n"
                "<equation>w'_1 = 3 + (0.1 × 1)</equation>\n"
                "<equation>z = ∑_(i=1)^n(w_i x_i) + b</equation>\n"
                "<equation>h1 = f(w_(11) x1 + b1)</equation>",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.object(settings, "OUTPUT_DIR", output_dir):
                FileExporter.save_word_document(sections, "equation_regression")

            with zipfile.ZipFile(output_dir / "equation_regression.docx") as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertNotIn("<m:t>_</m:t>", document_xml)
        self.assertNotIn("∑_(", document_xml)
        self.assertNotIn("w_(", document_xml)
        self.assertIn("<m:sSub>", document_xml)


if __name__ == "__main__":
    unittest.main()
