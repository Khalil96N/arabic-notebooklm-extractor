import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from docx import Document
from lxml import etree

from app.services import russian_lexicon as lex
from app.exporters.russian_lexicon import save_dictionary_document


def source(russian, arabic, english, pronunciation="لَفْظ", **extra):
    return dict(russian=russian, arabic=arabic, english=english,
                pronunciation=pronunciation, lectures=[1], category="أخرى", **extra)


def state(*records):
    return {"vocabulary": [dict(record, order=i+1) for i, record in enumerate(records)],
            "lectures": {"1": {"source_name":"1.mp3"}}}


def entries(data):
    return {e["id"]: e for e in lex.build_lexicon(data)["entries"]}


class RussianLexiconTests(unittest.TestCase):
    def test_lossless_lemma_merge_preserves_original_records_and_reviewed_pronunciation(self):
        data = state(source("Учить", "يتعلم أو يعلّم", "learn; teach"),
                     source("Учит", "يعلّم", "He teaches", "اللَّفْظُ المُرَاجَع", pronunciation_reviewed=True),
                     source("Учиться", "يدرس", "study"), source("Учатся", "يدرسون", "They study"))
        before = copy.deepcopy(data)
        result = lex.build_lexicon(data)
        lex.validate_lexicon(result)
        self.assertEqual(before, data)
        by_id = {e["id"]:e for e in result["entries"]}
        self.assertEqual({"INFN:учить", "INFN:учиться"}, set(by_id))
        self.assertEqual(4, sum(len(e["sources"]) for e in result["entries"]))
        rows = by_id["INFN:учить"]["conjugation"][0]["rows"]
        self.assertEqual([p[0] for p in lex.PERSONS], [r["label"] for r in rows])
        self.assertEqual("اللَّفْظُ المُرَاجَع", rows[2]["pronunciation"])

    def test_present_has_six_persons_and_perfective_is_not_present(self):
        by_id = entries(state(source("Пить", "يشرب", "drink"), source("Купить", "يشتري", "buy")))
        rows = by_id["INFN:пить"]["conjugation"][0]["rows"]
        self.assertEqual(["пью", "пьёшь", "пьёт", "пьём", "пьёте", "пьют"], [lex.key(r["russian"]) for r in rows])
        self.assertEqual([], by_id["INFN:купить"]["conjugation"])

    def test_imperative_is_second_person_not_inclusive_and_not_future(self):
        by_id = entries(state(source("Дай", "أعط", "Give (imperative)"), source("Сравните", "قارنوا", "Compare")))
        give = by_id["INFN:дать"]["conjugation"]
        self.assertEqual(["الأمر"], [p["label"] for p in give])
        self.assertEqual(["дай", "дайте"], [lex.key(r["russian"]) for r in give[0]["rows"]])
        self.assertEqual(["الأمر"], [p["label"] for p in by_id["INFN:сравнить"]["conjugation"]])

    def test_only_attested_other_tenses_are_expanded(self):
        by_id = entries(state(source("Работал", "عمل", "Worked (masculine)"), source("Пить", "يشرب", "drink")))
        self.assertEqual(["المضارع", "الماضي"], [p["label"] for p in by_id["INFN:работать"]["conjugation"]])
        self.assertEqual(4, len(by_id["INFN:работать"]["conjugation"][1]["rows"]))
        self.assertEqual(["المضارع"], [p["label"] for p in by_id["INFN:пить"]["conjugation"]])

    def test_six_cases_both_numbers_and_preposition_disambiguation(self):
        by_id = entries(state(source("Школа", "مدرسة", "school"), source("В школе", "في المدرسة", "At school"),
                              source("В школу", "إلى المدرسة", "To school")))
        school = by_id["NOUN:школа"]
        self.assertEqual(6, len(school["declension"]))
        self.assertTrue(all(r["sg"] and r["pl"] for r in school["declension"]))
        usage = {lex.key(u["russian"]):u for u in school["usage"] if u.get("source_id")}
        self.assertEqual("loct", usage["в школе"]["case"])
        self.assertEqual("accs", usage["в школу"]["case"])
        self.assertEqual("школу", lex.key(school["declension"][3]["sg"]["russian"]))

    def test_plural_only_indeclinable_and_irregular_nouns(self):
        by_id = entries(state(source("Кофе", "قهوة", "coffee"), source("Шахматы", "شطرنج", "chess"),
                              source("Ребёнок", "طفل", "child"), source("Стул", "كرسي", "chair")))
        coffee = by_id["NOUN:кофе"]["declension"]
        self.assertTrue(all(lex.key(r["sg"]["russian"]) == "кофе" and r["pl"] is None for r in coffee))
        self.assertTrue(all(r["sg"] is None and r["pl"] for r in by_id["NOUN:шахматы"]["declension"]))
        self.assertEqual("дети", lex.key(by_id["NOUN:ребёнок"]["declension"][0]["pl"]["russian"]))
        self.assertEqual("стулья", lex.key(by_id["NOUN:стул"]["declension"][0]["pl"]["russian"]))

    def test_aliases_are_merged_only_when_all_resolve_to_same_lexeme(self):
        by_id = entries(state(source("Книга / Книги", "كتاب / كتب", "Book / Books"),
                              source("Сын / Дочь", "ابن / ابنة", "Son / Daughter"),
                              source("Учу / Учусь / Учится", "صيغ مختلفة", "different verbs")))
        self.assertIn("NOUN:книга", by_id)
        self.assertIn("NOUN:сын", by_id)
        self.assertIn("NOUN:дочь", by_id)
        self.assertIn("INFN:учить", by_id)
        self.assertIn("INFN:учиться", by_id)
        self.assertEqual("Сын / Дочь", by_id["NOUN:сын"]["sources"][0]["russian"])
        self.assertTrue(by_id["NOUN:дочь"]["source_refs"])

    def test_homographs_follow_course_meaning(self):
        by_id = entries(state(source("Стой", "قف", "Stop"), source("Стоит", "يكلّف", "Costs (singular)"),
                              source("Душ", "دش", "Shower"), source("Математика", "رياضيات", "Mathematics"),
                              source("Яна", "يانا اسم علم مؤنث", "Yana (female name)"),
                              source("Маркер", "قلم تحديد", "Marker"), source("Пушкин", "اسم شخص", "Pushkin")))
        self.assertIn("INFN:стоять", by_id)
        self.assertIn("INFN:стоить", by_id)
        self.assertIn("NOUN:душ", by_id)
        self.assertIn("NOUN:математика", by_id)
        self.assertIn("NOUN:яна", by_id)
        self.assertEqual("маркеры", lex.key(by_id["NOUN:маркер"]["declension"][0]["pl"]["russian"]))
        self.assertFalse(by_id["NOUN:маркер"]["grammar"]["animate"])
        self.assertTrue(by_id["NOUN:пушкин"]["grammar"]["animate"])
        self.assertEqual("пушкиным", lex.key(by_id["NOUN:пушкин"]["declension"][4]["sg"]["russian"]))

    def test_thematic_families_put_opposites_and_related_verbs_together(self):
        result = lex.build_lexicon(state(source("Учиться", "يدرس", "study"), source("Писать", "يكتب", "write"),
                                         source("Учить", "يتعلم", "learn"), source("Изучать", "يدرس مادة", "study")))
        ids = [e["id"] for e in result["entries"]]
        a = ids.index("INFN:учить")
        self.assertEqual(["INFN:учить", "INFN:учиться", "INFN:изучать"], ids[a:a+3])

    def test_noun_homonyms_keep_course_animacy_gender_and_number(self):
        by_id = entries(state(source("Бот", "قارب", "Boat"), source("Моль", "عثة", "Moth"),
                              source("Коньки", "أحذية تزلج", "Ice skates"), source("Мак", "خشخاش", "Poppy"),
                              source("Волга", "نهر الفولغا", "Volga river")))
        for lemma, sg, pl in (("бот", "бот", "боты"), ("конёк", "конёк", "коньки")):
            item = by_id["NOUN:"+lemma]
            self.assertFalse(item["grammar"]["animate"])
            self.assertEqual(sg, lex.key(item["declension"][3]["sg"]["russian"]))
            self.assertEqual(pl, lex.key(item["declension"][3]["pl"]["russian"]))
        moth = by_id["NOUN:моль"]
        self.assertEqual("femn", moth["grammar"]["gender"])
        self.assertEqual("молью", lex.key(moth["declension"][4]["sg"]["russian"]))
        self.assertFalse(by_id["NOUN:мак"]["grammar"]["proper_name"])
        self.assertFalse(by_id["NOUN:мак"]["grammar"]["indeclinable"])
        self.assertFalse(by_id["NOUN:мак"]["review_flags"])
        self.assertEqual("маки", lex.key(by_id["NOUN:мак"]["declension"][0]["pl"]["russian"]))
        self.assertTrue(by_id["NOUN:волга"]["grammar"]["sg_only"])

    def test_uncertain_morphology_is_not_silently_published(self):
        result = lex.build_lexicon(state(source("Квазислово", "لفظ غير موثق", "unknown word")))
        self.assertEqual("PHRASE", result["entries"][0]["pos"])
        result["unresolved"] = [{"id":"NOUN:пример", "flags":["stress"]}]
        with self.assertRaisesRegex(ValueError, "تدقيق"):
            lex.ensure_ready_for_export(result)

    def test_cache_invalidates_on_source_change(self):
        data = state(source("Книга", "كتاب", "book"))
        with tempfile.TemporaryDirectory() as folder:
            first = lex.get_lexicon(data, Path(folder))
            with patch.object(lex, "build_lexicon", side_effect=AssertionError("cache miss")):
                self.assertEqual(first, lex.get_lexicon(data, Path(folder)))
            data["vocabulary"].append(dict(source("Школа", "مدرسة", "school"), order=2))
            second = lex.get_lexicon(data, Path(folder))
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(2, second["source_count"])

    def test_document_has_hyperlinked_index_no_lecture_column_and_separate_paradigms(self):
        result = lex.build_lexicon(state(source("Учить", "يعلّم", "teach"), source("Школа", "مدرسة", "school"),
                                         source("Жёлтая", "صفراء", "Yellow")))
        with tempfile.TemporaryDirectory() as folder:
            path = save_dictionary_document(result, Path(folder))
            document = Document(path)
            text = "\n".join(p.text for p in document.paragraphs) + "\n" + "\n".join(c.text for t in document.tables for r in t.rows for c in r.cells)
            self.assertTrue(path.name.startswith("قاموس مفردات"))
            self.assertNotIn("المحاضرات / المصدر", text)
            self.assertIn("المفرد ولفظه", text)
            self.assertIn("التصريف الروسي", text)
            with ZipFile(path) as package:
                root = etree.fromstring(package.read("word/document.xml"))
            ns = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            anchors = root.xpath("//w:hyperlink/@w:anchor", namespaces=ns)
            bookmarks = set(root.xpath("//w:bookmarkStart/@w:name", namespaces=ns))
            self.assertTrue(anchors)
            self.assertTrue(set(anchors) <= bookmarks)
            self.assertTrue(all(len(t.rows[0]._tr.xpath("./w:trPr/w:tblHeader")) == 1 for t in document.tables))
            self.assertTrue(all(len(t.columns) in (2, 3, 4) for t in document.tables))
            for table in document.tables:
                if len(table.columns) == 2:
                    from docx.text.paragraph import Paragraph
                    meaning = Paragraph(table._tbl.getprevious(), document._body)
                    self.assertTrue(meaning.paragraph_format.keep_with_next)

    def test_override_file_has_no_duplicate_keys(self):
        def unique(pairs):
            self.assertEqual(len(pairs), len(dict(pairs)), "Duplicate override keys")
            return dict(pairs)
        json.loads(lex.OVERRIDES_FILE.read_text(encoding="utf-8"), object_pairs_hook=unique)

    def test_common_nouns_are_not_mistaken_for_personal_names(self):
        by_id = entries(state(source("Боб", "حبة فول", "Bean"), source("Бобы", "فول", "Beans"), source("Роза", "وردة", "Rose")))
        for entry in by_id.values():
            self.assertFalse(entry["grammar"]["proper_name"])
            self.assertTrue(all(r["pl"] for r in entry["declension"]))

    def test_moving_stress_does_not_reuse_plural_pronunciation_for_genitive(self):
        by_id = entries(state(source("Место", "مكان", "place"), source("Места", "أماكن", "Places", "مَسْتَا", pronunciation_reviewed=True)))
        rows = by_id["NOUN:место"]["declension"]
        self.assertNotEqual(rows[0]["pl"]["russian"], rows[1]["sg"]["russian"])
        self.assertNotEqual(rows[0]["pl"]["pronunciation"], rows[1]["sg"]["pronunciation"])

    def test_math_noun_and_reviewed_modern_loans_have_complete_cases(self):
        by_id = entries(state(source("Уменьшаемое", "المطروح منه", "Minuend"), source("Маркетплейс", "سوق إلكتروني", "marketplace")))
        for target in ("NOUN:уменьшаемое", "NOUN:маркетплейс"):
            self.assertIn(target, by_id)
            self.assertEqual(6, len(by_id[target]["declension"]))
            self.assertTrue(all(r["sg"] and r["pl"] for r in by_id[target]["declension"]))

    def test_possessive_pronoun_is_not_lost_inside_personal_pronoun(self):
        by_id = entries(state(source("Он", "هو", "He"), source("Его", "له", "His"), source("Их", "لهم", "Their")))
        self.assertEqual({"NPRO:он", "NPRO:его", "NPRO:их"}, set(by_id))

    def test_reference_overrides_incorrect_prediction_for_unknown_verb(self):
        by_id = entries(state(source("Парковать", "يركن السيارة", "park")))
        rows = by_id["INFN:парковать"]["conjugation"][0]["rows"]
        self.assertEqual(["паркую", "паркуешь", "паркует", "паркуем", "паркуете", "паркуют"], [lex.key(r["russian"]) for r in rows])


if __name__ == "__main__":
    unittest.main()
