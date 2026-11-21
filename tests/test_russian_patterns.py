import copy
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from docx import Document
from app.exporters.russian_lexicon import save_dictionary_document
from app.services.russian_patterns import pattern_groups, verb_pattern_groups, paradigm_shape
from tests.test_russian_lexicon import entries, source, state


class RussianPatternsTests(unittest.TestCase):
    def test_same_noun_pattern_has_one_model_without_mutating_the_cache(self):
        by_id = entries(state(source("Группа", "مجموعة", "Group"), source("Школа", "مدرسة", "School")))
        original = copy.deepcopy(by_id)
        groups = pattern_groups(list(by_id.values()))
        self.assertEqual(1, len(groups))
        self.assertEqual(1, len(groups[0]["members"]))
        self.assertEqual(original, by_id)

    def test_stem_changes_animacy_and_moving_stress_do_not_share_a_model(self):
        by_id = entries(state(source("Стол", "طاولة", "Table"), source("Стул", "كرسي", "Chair")))
        self.assertEqual(2, len(pattern_groups(list(by_id.values()))))
        by_id = entries(state(source("Группа", "مجموعة", "Group"), source("Школа", "مدرسة", "School")))
        school = by_id["NOUN:школа"]
        school["declension"][2]["sg"]["russian"] = "школе́"
        self.assertEqual(2, len(pattern_groups(list(by_id.values()))))

    def test_present_is_not_repeated_because_only_one_member_has_past(self):
        by_id = entries(state(source("Читать", "يقرأ", "Read"), source("Работал", "عمل", "He worked")))
        groups = verb_pattern_groups(list(by_id.values()))
        present = [g for g in groups if g["label"] == "المضارع"]
        self.assertEqual(1, len(present))
        self.assertEqual(1, len(present[0]["members"]))
        self.assertEqual(1, len([g for g in groups if g["label"] == "الماضي"]))
        coverage = Counter((e["id"], g["label"]) for g in groups for e in [g["model"]]+g["members"])
        expected = Counter((e["id"], p["label"]) for e in by_id.values() for p in e["conjugation"])
        self.assertEqual(expected, coverage)

    def test_imperative_similarity_does_not_assert_same_future(self):
        by_id = entries(state(source("Дам", "سأعطي", "I will give"), source("Дай", "أعط", "Give"),
                              source("Послушайте", "استمعوا", "Listen"), source("Войти", "يدخل", "Enter")))
        groups = verb_pattern_groups(list(by_id.values()))
        future = [g for g in groups if g["label"] == "المستقبل"]
        self.assertEqual({"INFN:дать"}, {e["id"] for g in future for e in [g["model"]]+g["members"]})
        infinitives = [g for g in groups if g["label"] == "المصدر"]
        self.assertEqual(1, len(infinitives))
        self.assertFalse(infinitives[0]["members"])

    def test_docx_replaces_repeated_noun_paradigm_with_a_member_list(self):
        from app.services.russian_lexicon import build_lexicon
        result = build_lexicon(state(source("Группа", "مجموعة", "Group"), source("Школа", "مدرسة", "School")))
        with tempfile.TemporaryDirectory() as folder:
            doc = Document(save_dictionary_document(result, Path(folder)))
        self.assertEqual(2, len([t for t in doc.tables if len(t.columns) == 3]))  # case guide and one model
        self.assertEqual(1, len([t for t in doc.tables if len(t.columns) == 4]))
        self.assertTrue(any("على النمط نفسه" in p.text for p in doc.paragraphs))


if __name__ == "__main__":
    unittest.main()
