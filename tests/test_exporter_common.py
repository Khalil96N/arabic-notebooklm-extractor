import unittest

from app.exporters.common import (
    normalize_implicit_lists,
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


if __name__ == "__main__":
    unittest.main()
