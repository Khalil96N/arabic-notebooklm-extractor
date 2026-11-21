import copy
import unittest
from app.services.russian_flat_vocabulary import display_russian, review_vocabulary, final_devoicing
from app.exporters.russian_flat_vocabulary import lecture_label


def word(ru, en, ar="معنى", pron="لفظ", lectures=None):
    return dict(russian=ru, english=en, arabic=ar, pronunciation=pron,
                lectures=lectures or [], category="أخرى", order=1)


class FlatVocabularyTests(unittest.TestCase):
    def test_devoicing_does_not_touch_sonorants_or_connected_speech(self):
        self.assertEqual("كُوتْ", final_devoicing("Код", "كُودْ"))
        self.assertEqual("رُوبْلْ", final_devoicing("Рубль", "رُوبْلْ"))
        self.assertEqual("لفظ", final_devoicing("Мой друг был", "لفظ"))

    def test_gender_only_nouns(self):
        self.assertEqual("Словарь (он)", display_russian("Словарь"))
        self.assertEqual("Тетрадь (она) / Тетради", display_russian("Тетрадь / Тетради"))
        self.assertEqual("Моль (она)", display_russian("Моль"))
        self.assertEqual("Моль (он)", display_russian("Моль", "Mole (unit)"))
        for value in ("Читать", "Пять", "Восемь", "Жаль", "Добрый день"):
            self.assertEqual(value, display_russian(value))

    def test_corrects_mixed_script_preserving_every_source(self):
        rows = [word("Буكвы", "Letters", lectures=[3]), word("Буквы", "Letters", lectures=[4])]
        original = copy.deepcopy(rows)
        review = review_vocabulary(rows)
        self.assertEqual(original, rows)
        self.assertEqual(1, review["row_count"])
        self.assertEqual([0, 1], review["vocabulary"][0]["source_indices"])
        self.assertEqual([3, 4], review["vocabulary"][0]["lectures"])

    def test_lecture_33_soft_sign_nouns_and_city_names(self):
        for noun in ("Казань", "Астрахань", "Тверь", "Рязань", "Пермь", "Поверхность", "Жизнь", "Крепость"):
            self.assertEqual(f"{noun} (она)", display_russian(noun))
        for noun in ("Корабль", "Портфель", "Спектакль", "Суздаль", "Ярославль"):
            self.assertEqual(f"{noun} (он)", display_russian(noun))
        self.assertEqual("Казань (она) / В Казани", display_russian("Казань / В Казани"))
        self.assertEqual("Жить", display_russian("Жить"))
        self.assertEqual("В Перми", display_russian("В Перми"))
        self.assertEqual("Сибирь (она)", display_russian("Сибирь"))
        self.assertEqual("Игорь (он)", display_russian("Игорь"))

    def test_attested_group_absorbs_only_matching_meanings(self):
        rows = [word("Дом", "House", "بيت", lectures=[1]),
                word("Дома", "At home", "في البيت", lectures=[2]),
                word("Дом / Дома", "House / Houses", "بيت / بيوت", "دوم / دما", [3])]
        review = review_vocabulary(rows)
        self.assertEqual(2, review["row_count"])
        self.assertEqual({"Дома", "Дом / Дома"}, {r["russian"] for r in review["vocabulary"]})
        self.assertEqual([1, 3], next(r for r in review["vocabulary"] if "/" in r["russian"])["lectures"])

    def test_lecture_41_mathematical_soft_sign_nouns(self):
        self.assertEqual("Степень (она)", display_russian("Степень"))
        self.assertEqual("Показатель (он)", display_russian("Показатель"))
        self.assertEqual("Показатель степени", display_russian("Показатель степени"))
        self.assertEqual("В степени", display_russian("В степени"))

    def test_lecture_43_stove_noun_not_homographic_bake_verb(self):
        self.assertEqual("Писатель (он)", display_russian("Писатель", "Writer"))
        self.assertEqual("Внимательность (она)", display_russian("Внимательность", "Attentiveness"))
        self.assertEqual("Печь (она)", display_russian("Печь", "Stove; oven"))
        self.assertEqual("Печь (она)", display_russian("Печь", "An oven"))
        self.assertEqual("Печь", display_russian("Печь", "To bake in an oven"))
        self.assertEqual("Топить печь", display_russian("Топить печь", "To heat the stove"))

    def test_stressed_homographs_not_merged(self):
        rows = [word("до́ма", "At home"), word("дома́", "Houses")]
        self.assertEqual(2, review_vocabulary(rows)["row_count"])

    def test_lecture_44_root_gender_only_at_headword(self):
        self.assertEqual("Корень (он)", display_russian("Корень", "Root"))
        self.assertEqual("Квадратный корень", display_russian("Квадратный корень", "Square root"))

    def test_legacy_provenance_not_lost_when_modern_word_merges(self):
        legacy = word("Сын", "Son", "ابن")
        legacy["source_note"] = "الجدول القديم"
        rows = [legacy, word("Сын / Дочь", "Son / Daughter", "ابن / ابنة", "سين / دوتش", [3])]
        review = review_vocabulary(rows)
        self.assertIn("الجدول القديم", review["vocabulary"][0]["legacy_sources"])
        self.assertEqual("1-3, 7 + الجدول القديم", lecture_label({"lectures":[1,2,3,7], "legacy_sources":["الجدول القديم"]}))


if __name__ == "__main__":
    unittest.main()
