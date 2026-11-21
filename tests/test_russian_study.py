import copy
from pathlib import Path
import tempfile
import unittest

from docx import Document
from docx.oxml.ns import qn

from app.exporters.russian_lexicon import save_dictionary_document
from app.services.russian_lexicon import build_lexicon
from app.services.russian_study import build_study_index, validate_study_index, displayed_stress_notes, displayed_exceptions
from tests.test_russian_lexicon import source, state


def prepared(*words):
    return build_lexicon(state(*(source(*word) for word in words)))


class RussianStudyTests(unittest.TestCase):
    def test_shared_noun_model_is_reversible_without_changing_sources(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Школа", "مدرسة", "School"))
        before = copy.deepcopy(lex)
        index = build_study_index(lex)
        self.assertEqual(1, len(index["models"]))
        self.assertEqual(24, validate_study_index(lex, index))
        self.assertEqual(before, lex)

    def test_stress_difference_is_explicit_not_another_complete_model(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Школа", "مدرسة", "School"))
        school = next(e for e in lex["entries"] if e["id"] == "NOUN:школа")
        school["declension"][2]["sg"]["russian"] = "школе́"
        index = build_study_index(lex)
        self.assertEqual(1, len(index["models"]))
        self.assertTrue(any(displayed_stress_notes(b) for b in index["bindings"].values()))
        self.assertEqual(24, validate_study_index(lex, index))

    def test_irregular_plural_and_indeclinables_are_not_guessed(self):
        lex = prepared(("Ребёнок", "طفل", "Child"), ("Студент", "طالب", "Student"), ("Кофе", "قهوة", "Coffee"))
        index = build_study_index(lex)
        self.assertFalse(index["bindings"]["NOUN:кофе"])
        self.assertNotEqual(index["bindings"]["NOUN:ребёнок"][0]["code"], index["bindings"]["NOUN:студент"][0]["code"])
        validate_study_index(lex, index)

    def test_one_spelling_difference_in_multiple_cases_does_not_create_a_table(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Книга", "كتاب", "Book"))
        index = build_study_index(lex)
        self.assertEqual(1, len(index["models"]))
        differences = [item for bindings in index["bindings"].values() for item in displayed_exceptions(bindings)]
        self.assertEqual(1, len(differences))
        self.assertEqual(3, len(differences[0]["slots"]))

    def test_short_stress_note_must_itself_reconstruct_the_reviewed_form(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Школа", "مدرسة", "School"))
        school = next(e for e in lex["entries"] if e["id"] == "NOUN:школа")
        school["declension"][2]["sg"]["russian"] = "школе́"
        index = build_study_index(lex)
        exception = next(item for bindings in index["bindings"].values() for b in bindings for item in b["exceptions"] if item.get("stress_rule"))
        exception["stress_rule"] = ("النبر ثابت كما في الكلمة الأساسية" if exception["stress_rule"] != "النبر ثابت كما في الكلمة الأساسية" else "النبر على أول حركة من النهاية")
        with self.assertRaises(AssertionError):
            validate_study_index(lex, index)

    def test_ending_stress_is_not_expanded_into_a_redundant_full_paradigm(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Школа", "مدرسة", "School"), ("Страна", "بلد", "Country"))
        index = build_study_index(lex)
        self.assertEqual(1, len(index["models"]))
        country = index["bindings"]["NOUN:страна"]
        self.assertTrue(displayed_stress_notes(country))
        self.assertLess(len(displayed_exceptions(country)), 6)
        validate_study_index(lex, index)

    def test_tenses_keep_separate_links_and_perfectives_are_not_present(self):
        lex = prepared(("Читать", "يقرأ", "Read"), ("Работал", "عمل", "Worked"), ("Дам", "سأعطي", "I will give"))
        index = build_study_index(lex)
        read = index["bindings"]["INFN:читать"]
        work = index["bindings"]["INFN:работать"]
        self.assertEqual(read[0]["code"], next(b["code"] for b in work if b["label"] == "المضارع"))
        self.assertTrue(any(b["label"] == "الماضي" for b in work))
        self.assertEqual(["المستقبل"], [b["label"] for b in index["bindings"]["INFN:дать"]])

    def test_word_has_one_main_entry_and_all_internal_links_resolve(self):
        lex = prepared(("Группа", "مجموعة", "Group"), ("Школа", "مدرسة", "School"), ("Кофе", "قهوة", "Coffee"))
        with tempfile.TemporaryDirectory() as folder:
            path = save_dictionary_document(lex, Path(folder), layout="study")
            self.assertIn("نسخة الحفظ", path.name)
            doc = Document(path)
        root = doc._element
        names = [b.get(qn("w:name")) for b in root.iter(qn("w:bookmarkStart"))]
        ids = [b.get(qn("w:id")) for b in root.iter(qn("w:bookmarkStart"))]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(3, sum(name.startswith("study_word_") for name in names))
        for link in root.iter(qn("w:hyperlink")):
            if link.get(qn("w:anchor")):
                self.assertIn(link.get(qn("w:anchor")), names)
            if (link.get(qn("w:anchor")) or "").startswith("study_word_"):
                paragraph = link.getparent()
                self.assertEqual(qn("w:tbl"), paragraph.getnext().tag)
                self.assertIsNotNone(paragraph.find(qn("w:pPr")).find(qn("w:keepNext")))
        self.assertTrue(any("دليل التصريف" == p.text for p in doc.paragraphs))
        self.assertFalse(any("المحاضرات" in cell.text for table in doc.tables for cell in table.rows[0].cells))

    def test_previous_compact_export_stays_available_and_separate(self):
        lex = prepared(("Группа", "مجموعة", "Group"))
        with tempfile.TemporaryDirectory() as folder:
            compact = save_dictionary_document(lex, Path(folder))
            content = compact.read_bytes()
            study = save_dictionary_document(lex, Path(folder), layout="study")
            self.assertNotEqual(compact, study)
            self.assertEqual(content, compact.read_bytes())
            with self.assertRaises(ValueError):
                save_dictionary_document(lex, Path(folder), layout="study", expanded=True)


if __name__ == "__main__":
    unittest.main()
