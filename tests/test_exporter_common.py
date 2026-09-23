import unittest

from app.exporters.common import (
    clean_spacing,
    compact_russian_classroom_content,
    merge_adjacent_rule_chunks,
    normalize_implicit_lists,
    parse_rule_blocks,
    repair_notebooklm_math_artifacts,
    strip_repeated_heading,
)


class StripRepeatedHeadingTests(unittest.TestCase):
    def test_removes_same_heading_with_different_arabic_diacritics(self):
        text = (
            "أَوَّلًا: حُكْمُ التَّقْلِيدِ فِي الْعَقِيدَةِ\n"
            "نص الفقرة الكامل."
        )

        result = strip_repeated_heading(
            text,
            "أولاً: حكم التقليد في العقيدة",
        )

        self.assertEqual(result, "نص الفقرة الكامل.")

    def test_keeps_non_duplicate_first_line(self):
        text = "مقدمة الفقرة.\nبقية النص."

        result = strip_repeated_heading(
            text,
            "ثانياً: عنوان مختلف",
        )

        self.assertEqual(result, text)

    def test_removes_quoted_heading_prefix_and_keeps_inline_content(self):
        heading = "أولاً: مكانة صحيح الإمام البخاري وشروحه"
        text = (
            "«أَوَّلًا: مكانة صحيح الإمام البخاري وشروحه» "
            "بسم الله الرحمن الرحيم، نبدأ الدرس."
        )

        result = strip_repeated_heading(text, heading)

        self.assertEqual(
            result,
            "بسم الله الرحمن الرحيم، نبدأ الدرس.",
        )

    def test_removes_notebooklm_thoughts_artifact_before_repeated_heading(self):
        heading = "أولاً: مقدمة الدرس"
        text = (
            "Thoughts\n"
            "expand_more\n"
            "«أولاً: مقدمة الدرس» بسم الله الرحمن الرحيم، الحمد لله رب العالمين."
        )

        result = strip_repeated_heading(text, heading)

        self.assertEqual(
            result,
            "بسم الله الرحمن الرحيم، الحمد لله رب العالمين.",
        )

    def test_removes_nbx_marker_before_repeated_heading(self):
        text = "[[NBX-MATN-19-cdc31f6d]] Third: Title Body starts here."

        result = strip_repeated_heading(text, "Third: Title")

        self.assertEqual(result, "Body starts here.")

    def test_removes_consecutive_repeated_headings(self):
        heading = (
            "رابعاً: حكم اجتهاد النبي صلى الله عليه وسلم "
            "في الأحكام الشرعية"
        )
        repeated_heading = (
            "رَابِعًا: حُكْمُ اجْتِهَادِ النَّبِيِّ صَلَّى اللَّهُ عَلَيْهِ "
            "وَسَلَّمَ فِي الْأَحْكَامِ الشَّرْعِيَّةِ"
        )
        text = f"{repeated_heading}\n\n{repeated_heading}\nنص الفقرة."

        result = strip_repeated_heading(text, heading)

        self.assertEqual(result, "نص الفقرة.")


class CleanSpacingTests(unittest.TestCase):
    def test_unclosed_highlight_does_not_span_later_paragraphs(self):
        text = (
            "Important divisions: <highlight>\n"
            "The lecturer explains the first division.\n"
            "</highlight>\n"
            "The lecturer continues."
        )

        result = clean_spacing(text)

        self.assertEqual(
            result,
            "Important divisions: <highlight></highlight>\n"
            "The lecturer explains the first division.\n"
            "The lecturer continues.",
        )

    def test_unclosed_matn_does_not_span_later_paragraphs(self):
        text = "Quoted source: <matn>\nLecturer explanation."

        result = clean_spacing(text)

        self.assertEqual(
            result,
            "Quoted source: <matn></matn>\nLecturer explanation.",
        )

    def test_removes_bulleted_reference_artifact_numbers(self):
        text = (
            "- real item\n"
            "- 3\n"
            "-. continuation after artifact\n"
            "- 4\n"
            "-:\n"
            "- 4. body after artifact number\n"
            "- another real item"
        )

        result = clean_spacing(text)

        self.assertEqual(
            result,
            "- real item\n"
            "continuation after artifact\n"
            "body after artifact number\n"
            "- another real item",
        )

    def test_removes_trailing_citation_marker_with_no_following_newline(self):
        text = (
            "<pronunciation>اللفظ بالعربية: إِفْ</pronunciation>\n"
            "مقاطع الصوت: <russian>фа, фо, фу, фы, фи, фе</russian>\n"
            "20"
        )

        result = clean_spacing(text)

        self.assertEqual(
            result,
            "<pronunciation>اللفظ بالعربية: إِفْ</pronunciation>\n"
            "مقاطع الصوت: <russian>фа, фо, фу, фы, фи, фе</russian>",
        )

    def test_removes_notebooklm_followup_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f449 \u0647\u0644 \u062a\u0631\u063a\u0628 \u0641\u064a "
            "\u062a\u0641\u0631\u064a\u063a \u0627\u0644\u0633\u0624\u0627\u0644 "
            "\u0627\u0644\u062a\u0627\u0644\u064a\u061f\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_notebooklm_extract_and_transcribe_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f331 \u0647\u0644 \u062a\u0631\u063a\u0628 \u0641\u064a "
            "\u0627\u0633\u062a\u062e\u0631\u0627\u062c \u0648\u062a\u0641\u0631\u064a\u063a "
            "\u0627\u0644\u0642\u0633\u0645 \u0627\u0644\u062b\u0627\u0644\u062b "
            "\u0627\u0644\u0630\u064a \u064a\u062a\u0646\u0627\u0648\u0644 "
            "\"\u062d\u0642\u064a\u0642\u0629 \u0627\u0644\u062d\u064a\u0636 "
            "\u0648\u0627\u0644\u0646\u0641\u0627\u0633\"?\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_notebooklm_move_directly_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f4ca \u0647\u0644 \u062a\u0631\u063a\u0628 \u0641\u064a "
            "\u0627\u0644\u0627\u0646\u062a\u0642\u0627\u0644 "
            "\u0645\u0628\u0627\u0634\u0631\u0629 "
            "\u0644\u0627\u0633\u062a\u062e\u0631\u0627\u062c "
            "\u0648\u062a\u0641\u0631\u064a\u063a "
            "\u0627\u0644\u0642\u0633\u0645 "
            "\u0627\u0644\u062b\u0627\u0646\u064a\u061f\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_notebooklm_generic_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f4d6 \u0647\u0644 \u062a\u0631\u063a\u0628 \u0641\u064a "
            "\u062a\u062c\u0645\u064a\u0639 "
            "\u0647\u0630\u0647 \u0627\u0644\u0644\u0645\u062d\u0627\u062a "
            "\u0641\u064a \u062a\u0642\u0631\u064a\u0631 "
            "\u062f\u0631\u0627\u0633\u064a\u061f\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_notebooklm_table_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f4ca \u064a\u0645\u0643\u0646\u0646\u0627 "
            "\u0639\u0645\u0644 \u0645\u0642\u0627\u0631\u0646\u0629 "
            "\u062c\u062f\u0648\u0644\u064a\u0629 "
            "\u062a\u0644\u062e\u0635 \u0627\u0644\u0641\u0631\u0648\u0642.\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_exclamation_bullet_artifact_prefixes(self):
        text = "body before\n-! body after"

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_removes_notebooklm_transition_offer_lines(self):
        text = (
            "body before\n"
            "\U0001f4ca \u0623\u0633\u062a\u0637\u064a\u0639 "
            "\u0627\u0644\u0622\u0646 \u0627\u0644\u0627\u0646\u062a\u0642\u0627\u0644 "
            "\u0628\u0643 \u0645\u0628\u0627\u0634\u0631\u0629 \u0625\u0644\u0649 "
            "\u0627\u0644\u0642\u0633\u0645 \u0627\u0644\u062a\u0627\u0644\u064a "
            "(\u062a\u0627\u0633\u0639\u0627\u064b: "
            "\u0645\u0646\u0632\u0644\u0629 "
            "\u0627\u0644\u0645\u062a\u0648\u0646) "
            "\u0644\u0646\u0642\u0648\u0645 "
            "\u0628\u062a\u0641\u0631\u064a\u063a\u0647.\n"
            "body after"
        )

        result = clean_spacing(text)

        self.assertEqual(result, "body before\nbody after")

    def test_restores_missing_opening_angle_for_semantic_tags(self):
        text = "matn>قول صاحب المتن.</matn>\nsubheading>عنوان</subheading>"

        result = clean_spacing(text)

        self.assertEqual(
            result,
            "<matn>قول صاحب المتن.</matn>\n"
            "<subheading>عنوان</subheading>",
        )

    def test_repairs_russian_block_tag_typos_and_ui_artifacts(self):
        text = (
            "more_horiz:\n"
            "7:\n"
            "<russian>К к</russian> "
            "<pronunciation>اللفظ بالعربية: كا</pronifier> "
            "<translation>المعنى بالعربية: حرف الكاف</</translation>\n"
            "<russian>э и о</russian> "
            "<pronunciation>اللفظ بالعربية: إيه إي أو</pronunciation> "
            "<translation>المعنى بالعربية: تدريب</Clarification></translation>"
        )

        result = clean_spacing(text)

        self.assertNotIn("more_horiz", result)
        self.assertNotIn("7:", result)
        self.assertNotIn("pronifier", result)
        self.assertNotIn("Clarification", result)
        self.assertEqual(2, result.count("<pronunciation>"))
        self.assertEqual(2, result.count("</pronunciation>"))
        self.assertEqual(2, result.count("</translation>"))

    def test_expands_russian_pronunciation_shorthand_to_a_full_block(self):
        text = "<russian>Аи</russian> (آإي)"

        result = clean_spacing(text)

        self.assertIn("<pronunciation>اللفظ بالعربية: آإي</pronunciation>", result)
        self.assertIn("<translation>المعنى بالعربية:", result)


class NormalizeImplicitListsTests(unittest.TestCase):
    def test_bullets_items_after_a_clear_list_introduction(self):
        text = (
            "يمتاز الكتاب بخصائص، منها:\n"
            "دقة الترتيب.\n"
            "سهولة التناول.\n"
            "وقد ختم الشارح هذه الفقرة."
        )

        result = normalize_implicit_lists(text)

        self.assertEqual(
            result,
            "يمتاز الكتاب بخصائص، منها:\n"
            "- دقة الترتيب.\n"
            "- سهولة التناول.\n"
            "وقد ختم الشارح هذه الفقرة.",
        )

    def test_bullets_consecutive_highlighted_divisions(self):
        text = (
            "<highlight>الرأي الأول</highlight>: القول الأول.\n"
            "<highlight>الرأي الثاني</highlight>: القول الثاني.\n"
            "ثم انتقل الشارح إلى مسألة أخرى."
        )

        result = normalize_implicit_lists(text)

        self.assertEqual(
            result,
            "- <highlight>الرأي الأول</highlight>: القول الأول.\n"
            "- <highlight>الرأي الثاني</highlight>: القول الثاني.\n"
            "ثم انتقل الشارح إلى مسألة أخرى.",
        )


class CompactRussianClassroomContentTests(unittest.TestCase):
    def test_removes_student_turns_and_keeps_teacher_model(self):
        text = (
            "تقرأ المعلمة النموذج الصحيح:\n"
            "<russian>ма́ма</russian> "
            "<pronunciation>اللفظ بالعربية: ماما</pronunciation> "
            "<translation>المعنى بالعربية: أمي</translation>\n"
            "الطالب أحمد: <russian>ма́ма</russian> "
            "<pronunciation>اللفظ بالعربية: ماما</pronunciation> "
            "<translation>المعنى بالعربية: قراءة الطالب</translation>\n"
            "الطالب عمر: <russian>ма́ма</russian> "
            "<pronunciation>اللفظ بالعربية: ماما</pronunciation> "
            "<translation>المعنى بالعربية: قراءة الطالب</translation>"
        )

        result = compact_russian_classroom_content(text)

        self.assertEqual(1, result.count("<russian>ма́ма</russian>"))
        self.assertNotIn("الطالب أحمد", result)
        self.assertNotIn("الطالب عمر", result)

    def test_removes_individual_reading_request_without_russian_block(self):
        text = (
            "تطلب المعلمة من الطالب أحمد البدء في محاولة قراءة الحروف.\n"
            "تشرح المعلمة أن الحرف الساكن يحتاج إلى حرف متحرك."
        )

        result = compact_russian_classroom_content(text)

        self.assertNotIn("الطالب أحمد", result)
        self.assertIn("الحرف الساكن يحتاج إلى حرف متحرك", result)

    def test_keeps_new_teacher_correction_without_student_details(self):
        text = (
            "أخطأ الطالب في الحرف، فصححت المعلمة النطق: "
            "<russian>Л л</russian> "
            "<pronunciation>اللفظ بالعربية: إيل "
            "(نطقه الطالب مثل الإنجليزية)</pronunciation> "
            "<translation>المعنى بالعربية: حرف اللام</translation>"
        )

        result = compact_russian_classroom_content(text)

        self.assertTrue(result.startswith("<russian>Л л</russian>"))
        self.assertIn("اللفظ بالعربية: إيل", result)
        self.assertNotIn("نطقه الطالب", result)

    def test_removes_attendance_and_technical_chatter(self):
        text = (
            "تبدأ المعلمة تسجيل الحضور والتحقق من الميكروفون.\n"
            "<russian>До́брое у́тро</russian> "
            "<pronunciation>اللفظ بالعربية: دوبرايِه أوترا</pronunciation> "
            "<translation>المعنى بالعربية: صباح الخير</translation>"
        )

        result = compact_russian_classroom_content(text)

        self.assertNotIn("تسجيل الحضور", result)
        self.assertIn("<russian>До́брое у́тро</russian>", result)

    def test_removes_break_announcements_and_keeps_teaching(self):
        text = (
            "تعلن المعلمة عن فترة الاستراحة لمدة عشر دقائق.\n"
            "<russian>переры́в</russian> "
            "<pronunciation>اللفظ بالعربية: بيريريف</pronunciation> "
            "<translation>المعنى بالعربية: استراحة</translation>\n"
            "<russian>отдохни́те</russian> "
            "<pronunciation>اللفظ بالعربية: أتداخنيتي</pronunciation> "
            "<translation>المعنى بالعربية: استريحوا / خذوا قسطاً من الراحة</translation>\n"
            "بعد انقضاء الاستراحة تراجع المعلمة الحرف السابق.\n"
            "تشرح المعلمة أن الحرف П مهموس."
        )

        result = compact_russian_classroom_content(text)

        self.assertNotIn("الاستراحة", result)
        self.assertNotIn("переры́в", result)
        self.assertNotIn("отдохни́те", result)
        self.assertIn("الحرف П مهموس", result)

    def test_removes_named_attendees_but_keeps_lesson_summary(self):
        text = (
            "تراجع المعلمة التحيات مع الطلاب الحاضرين (عمر ورمزي)، "
            "ثم تشرح الفرق بين الصيغة الرسمية وغير الرسمية."
        )

        result = compact_russian_classroom_content(text)

        self.assertIn("تراجع المعلمة التحيات مع الطلاب", result)
        self.assertIn("الصيغة الرسمية وغير الرسمية", result)
        self.assertNotIn("عمر", result)
        self.assertNotIn("رمزي", result)

    def test_removes_platform_and_attendance_russian_items(self):
        text = (
            "<russian>Слышно?</russian> "
            "<pronunciation>اللفظ بالعربية: سليشْنا</pronunciation> "
            "<translation>المعنى بالعربية: هل الصوت مسموع؟</translation>\n"
            "<russian>Это какая группа?</russian> "
            "<pronunciation>اللفظ بالعربية: إيتا كاكايا غروبا</pronunciation> "
            "<translation>المعنى بالعربية: أي مجموعة هذه؟</translation>\n"
            "<russian>Нет зву́ка.</russian> "
            "<pronunciation>اللفظ بالعربية: نييت زفوكا</pronunciation> "
            "<translation>المعنى بالعربية: لا يوجد صوت</translation>\n"
            "<russian>Repeat, please.</russian> "
            "<pronunciation>اللفظ بالعربية: ريبيت بليز</pronunciation> "
            "<translation>المعنى بالعربية: كرروا من فضلكم</translation>\n"
            "<russian>Ру́сский алфави́т</russian> "
            "<pronunciation>اللفظ بالعربية: روسكي ألفافيت</pronunciation> "
            "<translation>المعنى بالعربية: الأبجدية الروسية</translation>"
        )

        result = compact_russian_classroom_content(text)

        self.assertNotIn("Слышно", result)
        self.assertNotIn("какая группа", result)
        self.assertNotIn("Нет зву́ка", result)
        self.assertNotIn("Repeat, please", result)
        self.assertIn("Ру́сский алфави́т", result)


class RepairNotebookLMMathArtifactsTests(unittest.TestCase):
    def test_restores_split_subscripts_and_y_hat(self):
        text = (
            "## القسم\n"
            "x\n\t\u200b، x\n\t\u200b: المدخلات.\n"
            "w\n\t\u200b و w\n\t\u200b: الأوزان.\n"
            "y\n^\n\t\u200b: التنبؤ."
        )

        result = repair_notebooklm_math_artifacts(text)

        self.assertIn("x₁، x₂: المدخلات", result)
        self.assertIn("w₁ و w₂: الأوزان", result)
        self.assertIn("ŷ: التنبؤ", result)
        self.assertNotIn("\u200b", result)


class ParseRuleBlocksTests(unittest.TestCase):
    def test_splits_multiple_subheading_blocks(self):
        text = (
            "<subheading>القاعدة الأولى</subheading>\nشرح أول\n"
            "<subheading>القاعدة الثانية</subheading>\nشرح ثانٍ"
        )

        blocks = parse_rule_blocks(text)

        self.assertEqual(
            [
                ("القاعدة الأولى", "<subheading>القاعدة الأولى</subheading>\nشرح أول"),
                ("القاعدة الثانية", "<subheading>القاعدة الثانية</subheading>\nشرح ثانٍ"),
            ],
            blocks,
        )

    def test_leading_content_without_a_subheading_keeps_a_none_title(self):
        text = "لا توجد قاعدة جديدة في هذا الجزء."

        blocks = parse_rule_blocks(text)

        self.assertEqual([(None, text)], blocks)

    def test_empty_text_returns_no_blocks(self):
        self.assertEqual([], parse_rule_blocks("   "))


class MergeAdjacentRuleChunksTests(unittest.TestCase):
    def test_merges_a_rule_split_across_two_chunks_into_one_block(self):
        chunk_one = (
            "<subheading>جنس الأسماء</subheading>\n"
            "تُقسم الأسماء إلى مذكر ومؤنث.\n"
            "<russian>стол</russian> <translation>طاولة (مذكر)</translation>"
        )
        chunk_two = (
            "<subheading>جنس الأسماء</subheading>\n"
            "<russian>книга</russian> <translation>كتاب (مؤنث)</translation>"
        )

        merged = merge_adjacent_rule_chunks([chunk_one, chunk_two])

        # Only one <subheading>جنس الأسماء</subheading> should remain.
        self.assertEqual(
            1,
            merged.count("<subheading>جنس الأسماء</subheading>"),
        )
        self.assertIn("стол", merged)
        self.assertIn("книга", merged)

    def test_does_not_merge_unrelated_consecutive_rules(self):
        chunk_one = "<subheading>جنس الأسماء</subheading>\nشرح."
        chunk_two = "<subheading>حالة الجمع</subheading>\nشرح آخر."

        merged = merge_adjacent_rule_chunks([chunk_one, chunk_two])

        self.assertEqual(2, merged.count("<subheading>"))
        self.assertIn("<subheading>جنس الأسماء</subheading>", merged)
        self.assertIn("<subheading>حالة الجمع</subheading>", merged)

    def test_fallback_no_new_rule_lines_are_never_merged_together(self):
        merged = merge_adjacent_rule_chunks(
            [
                "لا توجد قاعدة جديدة في هذا الجزء.",
                "لا توجد قاعدة جديدة في هذا الجزء.",
            ]
        )

        self.assertEqual(
            "لا توجد قاعدة جديدة في هذا الجزء.\n\n"
            "لا توجد قاعدة جديدة في هذا الجزء.",
            merged,
        )

    def test_matches_titles_despite_diacritics_and_alef_spelling(self):
        chunk_one = "<subheading>جِنْسُ الأَسْمَاءِ</subheading>\nشرح أول."
        chunk_two = "<subheading>جنس الاسماء</subheading>\nشرح إضافي."

        merged = merge_adjacent_rule_chunks([chunk_one, chunk_two])

        self.assertEqual(1, merged.count("<subheading>"))
        self.assertIn("شرح أول", merged)
        self.assertIn("شرح إضافي", merged)


if __name__ == "__main__":
    unittest.main()
