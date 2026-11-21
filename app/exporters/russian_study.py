"""Thematic study dictionary first, linked inflection reference last."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from app.exporters.russian_lexicon import (
    FONT, _bookmark, _cell, _compact_form, _direction, _heading,
    _link, _list_row, _paragraph, _row, _run, _table, _case_guide,
)
from app.services.russian_lexicon import SECTIONS, TOPICS, key, ensure_ready_for_export
from app.services.russian_study import build_study_index, displayed_exceptions, displayed_stress_notes, TENSES

CASE_NUMBERS = {"nomn": "1", "gent": "2", "datv": "3", "accs": "4", "ablt": "5", "loct": "6"}


def _slot_description(slots, entry):
    groups = defaultdict(list)
    for slot in slots:
        label, number = slot.split(":", 1)
        if label in ("sg", "pl"):
            groups["المفرد" if label == "sg" else "الجمع"].append(CASE_NUMBERS[number])
        else:
            paradigm = next(p for p in entry["conjugation"] if p["label"] == label)
            person = paradigm["rows"][int(number)]["label"]
            person = {"я":"أنا", "ты":"أنت", "он / она / оно":"هو وهي", "мы":"نحن", "вы":"أنتم أو الاحترام", "они":"هم"}.get(person, person)
            groups[label].append(person)
    return "؛ ".join(label + " " + "،".join(values) for label, values in groups.items())


def _grammar_label(entry):
    grammar = entry.get("grammar", {})
    labels = []
    if entry["pos"] == "NOUN":
        labels.append({"masc":"مذكر", "femn":"مؤنث", "neut":"محايد", "ms-f":"مشترك الجنس"}.get(grammar.get("gender"), ""))
        if grammar.get("indeclinable"):
            labels.append("غير متصرف")
        if grammar.get("sg_only"):
            labels.append("المفرد فقط بهذا المعنى")
        if grammar.get("pl_only"):
            labels.append("الجمع فقط")
        if grammar.get("animate"):
            labels.append("عاقل نحويًا")
    elif entry["pos"] == "INFN":
        labels.append("غير تام" if grammar.get("aspect") == "impf" else "تام لا مضارع له")
    return "، ".join(label for label in labels if label)


def _study_entries(document, entries, index, ordinal, word_anchors):
    table = _table(document, ("الروسية", "اللفظ بالعربية", "المعنى بالعربية", "English"), (4.6, 4.0, 4.8, 4.6))
    row_index = 0
    for entry in entries:
        ordinal += 1
        row = _list_row(table, row_index); row_index += 1
        head = entry["headword"]
        p = _cell(row.cells[0], head["russian"], rtl=False, size=12.5)
        p.runs[0].bold = True
        _bookmark(p, word_anchors[entry["id"]], 10000 + ordinal)
        bindings = index["bindings"][entry["id"]]
        if bindings:
            _run(p, "   ", size=10.5)
            for position, binding in enumerate(bindings):
                if position:
                    _run(p, "  ", size=10.5)
                label = binding["code"]
                if entry["pos"] == "INFN":
                    label += " " + binding["label"]
                _link(p, label, binding["anchor"])
        _cell(row.cells[1], head["pronunciation"], size=10.5)
        grammar = _grammar_label(entry)
        _cell(row.cells[2], entry["arabic"] + ("  (" + grammar + ")" if grammar else ""), size=11)
        _cell(row.cells[3], entry["english"], rtl=False, size=10.5)
        notes = list(dict.fromkeys(entry.get("notes", [])))
        notes += [_slot_description(note["slots"], entry) + ": " + note["rule"] for note in displayed_stress_notes(bindings)]
        exceptions = displayed_exceptions(bindings)
        if exceptions or notes:
            extra = _list_row(table, row_index); row_index += 1
            for main_cell in row.cells:
                for paragraph in main_cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
            cell = extra.cells[0].merge(extra.cells[-1])
            p = _cell(cell, "اختلافات عن النموذج  " if exceptions else "", size=10.5)
            for position, exception in enumerate(exceptions):
                if position:
                    _run(p, "   •   ", size=10.5, rtl=True)
                form = exception["form"]
                _run(p, _slot_description(exception["slots"], entry) + "  ", size=10.5, rtl=True)
                _run(p, form["russian"], size=12.5, bold=True)
                _run(p, "  " + form["pronunciation"], rtl=True, size=10.5)
            for position, note in enumerate(notes):
                if position or exceptions:
                    _run(p, "   •   ", size=10.5, rtl=True)
                _run(p, note, size=10.5, rtl=True)

        seen = {key(entry["lemma"])}
        if entry["pos"] not in ("NOUN", "INFN"):
            for source in entry["sources"]:
                identity = key(source["russian"])
                if identity in seen or source["source_id"] in entry.get("alias_source_ids", []):
                    continue
                seen.add(identity)
                extra = _list_row(table, row_index); row_index += 1
                _cell(extra.cells[0], source["russian"], rtl=False, size=12)
                _cell(extra.cells[1], source["pronunciation"], size=10.5)
                _cell(extra.cells[2], source["arabic"] if entry["pos"] == "NPRO" else "", size=10.5)
                _cell(extra.cells[3], source["english"] if entry["pos"] == "NPRO" else "", rtl=False, size=10.5)
        for usage in entry.get("usage", []):
            if key(usage["russian"]) in seen:
                continue
            seen.add(key(usage["russian"]))
            extra = _list_row(table, row_index); row_index += 1
            _cell(extra.cells[0], usage["russian"], rtl=False, size=12)
            _cell(extra.cells[1], usage["pronunciation"], size=10.5)
            case = {"nomn":1,"gent":2,"datv":3,"accs":4,"ablt":5,"loct":6,"loc2":6,"gen2":2}.get(usage.get("case"))
            _cell(extra.cells[2], usage["arabic"] + (f"، الحالة {case}" if case else ""), size=10.5)
            _cell(extra.cells[3], usage["english"], rtl=False, size=10.5)
    _paragraph(document, "", size=2, after=2)
    return ordinal


def _reference_model(document, model, number, word_anchors):
    entry = model["entry"]
    title = "نموذج " + model["code"] if entry["pos"] == "NOUN" else "نموذج " + model["code"] + " في " + model["label"]
    heading = _heading(document, title, 3, model["anchor"], 50000 + number)
    _run(heading, "   ", size=11)
    _run(heading, entry["headword"]["russian"], size=12.5, bold=True)
    if entry["pos"] == "INFN":
        # Noun nominative cells already repeat their headword pronunciation.
        _run(heading, "  " + entry["headword"]["pronunciation"], size=10.5, rtl=True)
    # A small return link in the heading cannot become an orphan paragraph,
    # and does not add a repeated navigation line to every reference model.
    _run(heading, "   ", size=10.5)
    _link(heading, "عودة للكلمة", word_anchors[entry["id"]])
    for color in heading._p[-1].iter(qn("w:color")):
        color.set(qn("w:val"), "000000")
    if entry["pos"] == "NOUN":
        table = _table(document, ("الحالة", "المفرد ولفظه", "الجمع ولفظه"), (3.7, 7.15, 7.15))
        for i, form in enumerate(entry["declension"]):
            row = _row(table, i)
            _cell(row.cells[0], form["label"], size=10.5)
            _compact_form(row.cells[1], form.get("sg"))
            _compact_form(row.cells[2], form.get("pl"))
    else:
        table = _table(document, ("الضمير أو الصيغة", "التصريف الروسي", "اللفظ بالعربية"), (4.0, 7.0, 7.0))
        for i, form in enumerate(entry["conjugation"][0]["rows"]):
            row = _row(table, i)
            _cell(row.cells[0], form["label"], rtl=not bool(re.search("[А-Яа-яЁё]", form["label"])), size=11)
            _cell(row.cells[1], form["russian"], rtl=False, size=12.5)
            _cell(row.cells[2], form["pronunciation"], size=11)


def save_study_dictionary_document(lexicon: dict, output_dir: Path, *, sample=False) -> Path:
    ensure_ready_for_export(lexicon)
    index = build_study_index(lexicon)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = "نموذج قاموس الحفظ الروسي.docx" if sample else f"قاموس مفردات اللغة الروسية - نسخة الحفظ - المحاضرات 1-{lexicon['max_lecture']}.docx"
    path = output_dir / name
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = section.bottom_margin = Cm(1.5)
    normal = document.styles["Normal"]
    normal.font.name = FONT; normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(3)
    for style in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        document.styles[style].font.name = FONT
        document.styles[style].font.color.rgb = RGBColor(0, 0, 0)
    title = document.add_paragraph(style="Title")
    borders = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right", "between", "bar"):
        border = OxmlElement("w:" + side); border.set(qn("w:val"), "nil"); borders.append(border)
    title._p.get_or_add_pPr().append(borders)
    _direction(title, True)
    _run(title, "قاموس مفردات اللغة الروسية للحفظ والمراجعة", size=23, bold=True, rtl=True)
    _paragraph(document, f"مفردات المحاضرات 1 إلى {lexicon['max_lecture']} مع دليل تصريف مرتبط", size=13, after=8)
    _paragraph(document, "ابدأ بجداول الكلمات المرتبة حسب الموضوع. تظهر الكلمة الأساسية مرة واحدة مع لفظها ومعناها بالعربية والإنجليزية. للاطلاع على التصريف اضغط رقم النموذج بجانب الكلمة، أو ابحث عن رقمه في الملحق عند استخدام النسخة المطبوعة.", after=6)
    _paragraph(document, "تظهر روابط التصريف باسم نموذج اسم أو نموذج فعل مع رقمه. النماذج تشرح النهايات المشتركة؛ أما الصيغ التي تختلف عنها في الكتابة فتظهر أسفل الكلمة مع لفظها، ويُوضح اختلاف النبر في ملاحظة. هذه الاختلافات مقدمة على النموذج. صفة المفرد فقط أو الجمع فقط تحدد العمود الذي ينطبق على الكلمة.", after=6)
    _paragraph(document, "اللفظ بالعربية تقريبي. راجع النطق المسموع، وانتبه للنبر فوق الحرف الروسي. للمراجعة اختبر نفسك بإخفاء أعمدة المعنى، ثم راجع الإجابة وكرر الكلمات على فترات.", after=6)
    _heading(document, "فهرس الأقسام", 1, "study_contents", 1)
    sections = defaultdict(lambda: defaultdict(list))
    for entry in lexicon["entries"]:
        sections[entry["section"]][entry["topic"]].append(entry)
    for position, name in enumerate(SECTIONS):
        if name in sections:
            p = _paragraph(document, "", after=2)
            _link(p, name, f"study_section_{position}")
    p = _paragraph(document, "", after=2)
    _link(p, "دليل تصريف الأسماء", "study_nouns")
    p = _paragraph(document, "", after=2)
    _link(p, "دليل تصريف الأفعال", "study_verbs")
    word_anchors = {entry["id"]: f"study_word_{n}" for n, entry in enumerate(lexicon["entries"], 1)}
    ordinal = 0
    for position, name in enumerate(SECTIONS):
        if name not in sections:
            continue
        heading = _heading(document, name, 1, f"study_section_{position}", 100 + position)
        if ordinal == 0:
            heading.paragraph_format.page_break_before = True
        for topic_number, topic in enumerate(TOPICS):
            if topic not in sections[name]:
                continue
            _heading(document, topic, 2, f"study_topic_{position}_{topic_number}", 1000 + position * 100 + topic_number)
            ordinal = _study_entries(document, sections[name][topic], index, ordinal, word_anchors)

    heading = _heading(document, "دليل التصريف", 1, "study_reference", 40000)
    heading.paragraph_format.page_break_before = True
    _link(_paragraph(document, "", after=3), "العودة إلى فهرس الأقسام", "study_contents")
    _paragraph(document, "كل نموذج مثال على النهايات المشتركة، لا يعني تطابق نبر جميع الكلمات معه. اقرأ اختلافات الكلمة في جدول الحفظ قبل تطبيق النموذج. لا تُسمّى صيغ مستقبل الفعل التام مضارعًا، ولا تُضاف أزمنة لم ترد في مادة الكورس.", after=6)
    _heading(document, "دليل تصريف الأسماء", 2, "study_nouns", 40001)
    _case_guide(document)
    _paragraph(document, "الأسماء غير المتصرفة تبقى كما هي؛ لذلك لا تحتاج نموذجًا. المفرد والجمع محدودان بالاستعمال الموضح بجانب كل كلمة. تتبع الأسماء العاقلة أحكام النصب الخاصة بها، ولا يُنقل حكم المكان أو الاتجاه من اسم إلى آخر دون سياقه.", after=5)
    for n, model in enumerate(index["models"], 1):
        if model["entry"]["pos"] == "NOUN":
            _reference_model(document, model, n, word_anchors)
    _heading(document, "دليل تصريف الأفعال", 2, "study_verbs", 40002)
    _paragraph(document, "اتبع رقم النموذج الخاص بالزمن أو الأمر المطلوب. تشابه فعلين في المضارع لا يعني أنهما يتشابهان في كل الأزمنة. الماضي أو المستقبل أو الأمر يظهر هنا عندما يكون قد ورد في الكورس.", after=5)
    for label_number, label in enumerate(TENSES):
        models = [(n, model) for n, model in enumerate(index["models"], 1) if model["entry"]["pos"] == "INFN" and model["label"] == label]
        if models:
            _heading(document, label, 2, f"study_tense_{label_number}", 41000 + label_number)
        for n, model in models:
            _reference_model(document, model, n, word_anchors)
    _heading(document, "المراجع اللغوية", 1, "study_references", 90000)
    for source in lexicon.get("references", []):
        p = _paragraph(document, "", rtl=False, after=3)
        _link(p, source["name"], source["url"], internal=False, rtl=False)
        _run(p, "  " + source["license"], size=10.5)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE"); footer._p.append(field)
    temporary = path.with_name(path.stem + ".tmp.docx")
    document.save(temporary)
    temporary.replace(path)
    return path
