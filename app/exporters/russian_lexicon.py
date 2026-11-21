"""Compact bilingual Word dictionary with independent per-lemma paradigms.

This module deliberately has no Settings or morphology dependency: a prepared
lexicon can be rendered with the bundled document runtime as well as the app.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from app.services.russian_lexicon import CASE_LABELS, SECTIONS, TOPICS, key, ensure_ready_for_export
from app.services.russian_patterns import pattern_groups, verb_pattern_groups

BLUE = "1F4E79"
PALE = "F0F5FA"
FONT = "Arial"


def _direction(paragraph, rtl: bool) -> None:
    props = paragraph._p.get_or_add_pPr()
    item = props.find(qn("w:bidi"))
    if item is None:
        item = OxmlElement("w:bidi"); props.append(item)
    item.set(qn("w:val"), "1" if rtl else "0")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
    # Use logical alignment: LibreOffice otherwise mirrors physical `right`
    # on importing an RTL paragraph. Word also honours `start` in RTL text.
    paragraph._p.get_or_add_pPr().find(qn("w:jc")).set(qn("w:val"), "start" if rtl else "left")


def _run(paragraph, text: str, *, rtl: bool = False, size: float = 11, bold: bool = False, color: str = "000000"):
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    props = run._r.get_or_add_rPr()
    fonts = props.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts"); props.append(fonts)
    for name in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn("w:" + name), FONT)
    for tag, val in (("rtl", "1" if rtl else "0"), ("szCs", str(round(size*2)))):
        el = OxmlElement("w:"+tag); el.set(qn("w:val"), val); props.append(el)
    return run


def _paragraph(document, text: str, *, rtl: bool = True, size: float = 11, bold: bool = False, keep: bool = False, after: float = 3):
    paragraph = document.add_paragraph()
    _direction(paragraph, rtl)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.05
    paragraph.paragraph_format.keep_with_next = keep
    _run(paragraph, text, rtl=rtl, size=size, bold=bold)
    return paragraph


def _bookmark(paragraph, name: str, number: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number)); start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd"); end.set(qn("w:id"), str(number))
    paragraph._p.insert(0, start); paragraph._p.append(end)


def _link(paragraph, text: str, target: str, *, internal: bool = True, rtl: bool = True) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE
    link = OxmlElement("w:hyperlink")
    if internal:
        link.set(qn("w:anchor"), target)
    else:
        relation = paragraph.part.relate_to(target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        link.set(qn("r:id"), relation)
    # Reuse normal run styling, then move it into the hyperlink.
    run = _run(paragraph, text, rtl=rtl, size=11, color=BLUE)
    paragraph._p.remove(run._r); link.append(run._r); paragraph._p.append(link)


def _heading(document, text: str, level: int, anchor: str, number: int):
    p = document.add_paragraph(style=f"Heading {level}")
    _direction(p, True)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(10 if level < 3 else 7)
    p.paragraph_format.space_after = Pt(4)
    _run(p, text, rtl=not bool(re.search("[А-Яа-яЁё]", text)), bold=True, size={1:19, 2:15, 3:14}[level])
    _bookmark(p, anchor, number)
    return p


def _cell(cell, text: str, *, rtl: bool = True, header: bool = False, size: float = 11):
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    _direction(p, rtl)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    _run(p, text, rtl=rtl, size=size, bold=header, color="FFFFFF" if header else "000000")
    return p


def _table(document, headers: tuple[str, ...], widths: tuple[float, ...]):
    table = document.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    properties = table._tbl.tblPr
    bidi = OxmlElement("w:bidiVisual"); bidi.set(qn("w:val"), "1"); properties.append(bidi)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "bottom", "left", "right", "insideH", "insideV"):
        item = OxmlElement("w:"+side)
        for name, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
            item.set(qn("w:"+name), value)
        borders.append(item)
    properties.append(borders)
    margins = OxmlElement("w:tblCellMar")
    for side, width in (("top", "36"), ("bottom", "36"), ("left", "65"), ("right", "65")):
        item = OxmlElement("w:"+side); item.set(qn("w:w"), width); item.set(qn("w:type"), "dxa"); margins.append(item)
    properties.append(margins)
    for i, width in enumerate(widths):
        table.columns[i].width = Cm(width)
        table.rows[0].cells[i].width = Cm(width)
        cell = table.rows[0].cells[i]
        fill = OxmlElement("w:shd"); fill.set(qn("w:fill"), BLUE); cell._tc.get_or_add_tcPr().append(fill)
        _cell(cell, headers[i], header=True, size=10.5)
    repeat = OxmlElement("w:tblHeader"); table.rows[0]._tr.get_or_add_trPr().append(repeat)
    for cell in table.rows[0].cells:
        cell.paragraphs[0].paragraph_format.keep_with_next = True
    return table


def _row(table, index: int):
    # Keep each short paradigm together. Besides easier review, this avoids a
    # native LibreOffice bidi-table pagination bug that can omit continued rows.
    for cell in table.rows[-1].cells:
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.keep_with_next = True
    row = table.add_row()
    props = row._tr.get_or_add_trPr()
    props.append(OxmlElement("w:cantSplit"))
    for i, cell in enumerate(row.cells):
        cell.paragraphs[0].paragraph_format.keep_with_next = False
        cell.width = table.columns[i].width
        if index % 2 == 0:
            fill = OxmlElement("w:shd"); fill.set(qn("w:fill"), PALE); cell._tc.get_or_add_tcPr().append(fill)
    return row


def _compact_form(cell, form: dict | None) -> None:
    p = _cell(cell, "", rtl=False)
    if form is None:
        _direction(p, True); _run(p, "لا تُستعمل", rtl=True, size=10.5)
        return
    _run(p, form["russian"], size=12.5, bold=True)
    _run(p, "  |  ", size=9, color="666666")
    _run(p, form["pronunciation"], rtl=True, size=10.5)


def _sense_line(document, entry: dict, *, keep: bool):
    p = _paragraph(document, "", keep=keep, after=4)
    _run(p, entry["arabic"], rtl=True, size=11)
    _run(p, "  |  ", size=10, color="666666")
    _run(p, entry["english"], size=10.5)
    return p


def _usage(document, usages: list[dict]) -> None:
    seen = set()
    for usage in usages:
        identity = key(usage["russian"])
        if identity in seen:
            continue
        seen.add(identity)
        p = _paragraph(document, "", rtl=False, after=2)
        _run(p, usage["russian"], size=12, bold=True)
        _run(p, "  |  ", size=10)
        _run(p, usage["pronunciation"], rtl=True, size=10.5)
        usage = dict(usage)
        case = {"nomn":1, "gent":2, "gen2":2, "datv":3, "accs":4, "ablt":5, "loct":6, "loc2":6}.get(usage.get("case"))
        if case:
            usage["arabic"] += f"، الحالة {case}"
        _sense_line(document, usage, keep=False)


def _entry(document, entry: dict, ordinal: int, *, model_label: str = "") -> None:
    p = _heading(document, entry["headword"]["russian"], 3, f"word_{ordinal}", 10000+ordinal)
    # Arabic page flow with an explicitly LTR Russian run.
    _direction(p, True)
    _run(p, "  ", size=10)
    _run(p, entry["headword"]["pronunciation"], rtl=True, size=11, bold=False)
    if model_label:
        _run(p, "  " + model_label, rtl=True, size=10.5, bold=False)
    structured = entry["pos"] in ("NOUN", "INFN")
    sense = _sense_line(document, entry, keep=structured)
    grammar = entry.get("grammar", {})
    if entry["pos"] == "NOUN":
        gender = {"masc":"مذكر", "femn":"مؤنث", "neut":"محايد", "ms-f":"مشترك الجنس"}.get(grammar.get("gender"), "")
        description = "اسم " + gender
        if grammar.get("animate"):
            description += "، عاقل نحويًا"
        if grammar.get("indeclinable"):
            description += "، غير متصرف"
        if grammar.get("sg_only"):
            description += "، المفرد فقط بهذا الاستعمال"
        if grammar.get("pl_only"):
            description += "، يستعمل بصيغة الجمع"
        if model_label:
            _run(sense, "  |  " + description, rtl=True, size=10)
        else:
            _paragraph(document, description, size=10.5, keep=True, after=3)
        table = _table(document, ("الحالة", "المفرد ولفظه", "الجمع ولفظه"), (3.7, 7.15, 7.15))
        for i, form in enumerate(entry["declension"]):
            row = _row(table, i)
            _cell(row.cells[0], form["label"], size=10.5)
            _compact_form(row.cells[1], form.get("sg"))
            _compact_form(row.cells[2], form.get("pl"))
    elif entry["pos"] == "INFN":
        label = "مصدر فعل غير تام" if grammar.get("aspect") == "impf" else "مصدر فعل تام"
        if grammar.get("reflexive"):
            label += "، ينتهي بـ ся أو сь"
        if model_label:
            _run(sense, "  |  " + label, rtl=True, size=10)
        else:
            _paragraph(document, label, size=10.5, keep=bool(entry["conjugation"]), after=3)
        for paradigm in entry["conjugation"]:
            if not model_label:
                _paragraph(document, paradigm["label"], bold=True, size=11, keep=True, after=2)
            table = _table(document, ("الضمير أو الصيغة", "التصريف الروسي", "اللفظ بالعربية"), (4.0, 7.0, 7.0))
            for i, form in enumerate(paradigm["rows"]):
                row = _row(table, i)
                _cell(row.cells[0], form["label"], rtl=bool(re.search("[\u0600-\u06ff]", form["label"])), size=11)
                _cell(row.cells[1], form["russian"], rtl=False, size=12.5)
                _cell(row.cells[2], form["pronunciation"], size=11)
    else:
        # Other parts of speech retain attested forms without manufacturing
        # adjective/pronoun paradigms that have not been requested.
        forms, seen = [], set()
        for source in entry["sources"]:
            if source["source_id"] in entry.get("alias_source_ids", []):
                continue
            identity = key(source["russian"])
            if identity == key(entry["lemma"]) or identity in seen:
                continue
            seen.add(identity)
            forms.append(source)
        if forms:
            sense.paragraph_format.keep_with_next = True
            pronoun = entry["pos"] == "NPRO"
            table = _table(document, ("الصيغة", "اللفظ بالعربية", "معنى الاستعمال", "English") if pronoun else ("الصيغ أو الاستعمالات الواردة", "اللفظ بالعربية"), (4.5, 4.0, 4.75, 4.75) if pronoun else (9.0, 9.0))
            for i, source in enumerate(forms):
                row = _row(table, i)
                _cell(row.cells[0], source["russian"], rtl=False, size=12)
                _cell(row.cells[1], source["pronunciation"], size=11)
                if pronoun:
                    _cell(row.cells[2], source["arabic"], size=10.5)
                    _cell(row.cells[3], source["english"], rtl=False, size=10.5)
    for note in dict.fromkeys(entry.get("notes", [])):
        _paragraph(document, note, size=10.5, after=3)
    _usage(document, entry.get("usage", []))


def _case_guide(document) -> None:
    _paragraph(document, "الصيغة الأساسية للاسم هي حالة الرفع. يتغير آخر الاسم حسب دوره في الجملة، ويظهر المفرد والجمع في الصف نفسه. اللفظ العربي تقريبي ويساعد على التذكر، ولا يغني عن الاستماع.", after=5)
    questions = (
        ("кто? что?", "مَن أو ما؟ للاسم بوصفه فاعلًا أو تسمية."),
        ("кого? чего?", "لمن أو لأي شيء؟ من استخداماته الإضافة والملكية والغياب."),
        ("кому? чему?", "لمن أو لأي شيء؟ للمتلقي أو الجهة بحسب التركيب."),
        ("кого? что?", "مَن أو ماذا؟ للمفعول به، ومع الاتجاه بعد حروف مناسبة."),
        ("кем? чем?", "بمَن أو بماذا؟ للأداة، ومع المصاحبة بعد с."),
        ("о ком? о чём? где?", "عن مَن أو ماذا؟ وللمكان مع в أو на بحسب المعنى."),
    )
    table = _table(document, ("الحالة", "السؤال الروسي", "الاستخدام المختصر"), (3.7, 5.3, 9.0))
    for i, (label, (question, meaning)) in enumerate(zip(CASE_LABELS, questions)):
        row = _row(table, i)
        _cell(row.cells[0], label, size=10.5)
        _cell(row.cells[1], question, rtl=False, size=11.5)
        _cell(row.cells[2], meaning, size=10.5)
    _paragraph(document, "حرف الجر والحالة يتبعان المعنى المقصود؛ لا نضع в أو на مع كل اسم آليًا. في عبارات المكان نميز المكان عن الاتجاه. بعض الاستعمالات لها صيغة محلية خاصة تُذكر عند ورودها.", after=6)


def _list_row(table, index):
    row = _row(table, index)
    # Lists may span pages; keep only the header with the first body row.
    if len(table.rows) > 2:
        for cell in table.rows[-2].cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next = False
    return row


def _compact_entries(document, entries, ordinal, *, members=False):
    table = _table(document, ("الروسية", "اللفظ بالعربية", "المعنى بالعربية", "English meaning"), (4.6, 4.0, 4.8, 4.6))
    row_index = 0
    for entry in entries:
        ordinal += 1
        row = _list_row(table, row_index); row_index += 1
        head = entry["headword"]
        p = _cell(row.cells[0], head["russian"], rtl=False, size=12.5)
        p.runs[0].bold = True
        _bookmark(p, f"word_{ordinal}", 10000+ordinal)
        _cell(row.cells[1], head["pronunciation"], size=10.5)
        arabic = entry["arabic"]
        notes = list(dict.fromkeys(entry.get("notes", [])))
        if notes:
            arabic += "\n" + "\n".join(notes)
        _cell(row.cells[2], arabic, size=11)
        _cell(row.cells[3], entry["english"], rtl=False, size=10.5)
        # Structured members intentionally omit their repeated paradigms.
        # Other parts retain attested forms, with contextual pronoun meanings.
        seen = {key(entry["lemma"])}
        if not members:
            for source in entry["sources"]:
                identity = key(source["russian"])
                if identity in seen or source["source_id"] in entry.get("alias_source_ids", []):
                    continue
                seen.add(identity)
                row = _list_row(table, row_index); row_index += 1
                _cell(row.cells[0], source["russian"], rtl=False, size=12)
                _cell(row.cells[1], source["pronunciation"], size=10.5)
                _cell(row.cells[2], source["arabic"] if entry["pos"] == "NPRO" else "", size=10.5)
                _cell(row.cells[3], source["english"] if entry["pos"] == "NPRO" else "", rtl=False, size=10.5)
        for usage in entry.get("usage", []):
            if key(usage["russian"]) in seen:
                continue
            seen.add(key(usage["russian"]))
            row = _list_row(table, row_index); row_index += 1
            _cell(row.cells[0], usage["russian"], rtl=False, size=12)
            _cell(row.cells[1], usage["pronunciation"], size=10.5)
            _cell(row.cells[2], usage["arabic"], size=10.5)
            _cell(row.cells[3], usage["english"], rtl=False, size=10.5)
    _paragraph(document, "", after=2, size=2)
    return ordinal


def save_dictionary_document(lexicon: dict, output_dir: Path, *, sample: bool = False, expanded: bool = False, layout: str = "compact") -> Path:
    if layout not in ("compact", "study"):
        raise ValueError(f"Unknown Russian dictionary layout: {layout}")
    if layout == "study":
        if expanded:
            raise ValueError("Expanded and study layouts cannot be combined")
        from app.exporters.russian_study import save_study_dictionary_document
        return save_study_dictionary_document(lexicon, output_dir, sample=sample)
    ensure_ready_for_export(lexicon)
    output_dir.mkdir(parents=True, exist_ok=True)
    max_lecture = lexicon["max_lecture"]
    path = output_dir / ("نموذج القاموس الروسي.docx" if sample else f"قاموس مفردات اللغة الروسية - المحاضرات 1-{max_lecture}.docx")
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
        border = OxmlElement("w:"+side); border.set(qn("w:val"), "nil"); borders.append(border)
    title._p.get_or_add_pPr().append(borders)
    _direction(title, True)
    _run(title, "قاموس مفردات اللغة الروسية", rtl=True, size=24, bold=True)
    _paragraph(document, f"مفردات المحاضرات 1 إلى {max_lecture} مرتبة للحفظ والمراجعة", size=13, after=10)
    _paragraph(document, "ابحث عن الكلمة بصيغتها الأساسية. لكل نمط تصريف نموذج كامل واحد، وتحته الكلمات التي تتبعه مع اللفظ والمعنى بالعربية والإنجليزية. تتجمع الكلمات داخل كل نموذج بحسب الموضوع، ولا تتكرر جداول التصريف لكل كلمة.", after=8)
    _paragraph(document, "الكلمات المدرجة تحت النموذج تتبع نهاياته ونمط نبره وتغيرات جذعه. عند وجود اختلاف تُفصل في نموذج آخر. أما الأسماء التي لا تتصرف فلا تتغير صيغتها، ويُذكر استعمال المفرد فقط أو الجمع فقط عند الحاجة.", after=8)
    _paragraph(document, "المضارع مستكمل للأفعال غير التامة. تظهر الأزمنة الأخرى والأمر عندما ترد في مادة الكورس. صيغ الأسماء مستكملة مرجعيًا، ولا يُضاف مفرد أو جمع غير مناسب للاستعمال.", after=8)
    _paragraph(document, "اللفظ المكتوب بالعربية تقريبي؛ الحروف پ وڤ وگ وژ تميز أصواتًا لا تمثلها العربية المعتادة بدقة. حافظ على مراجعة النطق المسموع.", after=8)
    _paragraph(document, "تُحفظ العبارات والأسماء المركبة بوحدتها، ولا تُفكك آليًا إلى كلمات منفصلة. يمكنك استعمال الفهرس للموضوعات، والبحث داخل Word للوصول مباشرة إلى كلمة بعينها.", after=8)
    toc = _heading(document, "فهرس الأقسام والموضوعات", 1, "contents", 1)
    sections = defaultdict(lambda: defaultdict(list))
    for entry in lexicon["entries"]:
        sections[entry["section"]][entry["topic"]].append(entry)
    for s_index, section_name in enumerate(SECTIONS):
        if section_name not in sections:
            continue
        p = _paragraph(document, "", after=3)
        _link(p, section_name, f"section_{s_index}")
        if not expanded:
            continue
        topics = [t for t in TOPICS if t in sections[section_name]]
        if not expanded and section_name in ("الأفعال", "الأسماء"):
            continue
        for t_index, topic in enumerate(topics):
            p = _paragraph(document, "", size=10.5, after=1)
            p.paragraph_format.right_indent = Cm(.6)
            _link(p, topic, f"topic_{s_index}_{t_index}")
    ordinal = 0
    for s_index, section_name in enumerate(SECTIONS):
        if section_name not in sections:
            continue
        p = _heading(document, section_name, 1, f"section_{s_index}", 100+s_index)
        p.paragraph_format.page_break_before = True
        nav = _paragraph(document, "", after=5)
        _link(nav, "العودة إلى الفهرس", "contents")
        if section_name == "الأسماء":
            _case_guide(document)
        if not expanded and section_name in ("الأفعال", "الأسماء"):
            all_entries = [entry for topic in TOPICS for entry in sections[section_name].get(topic, [])]
            groups = verb_pattern_groups(all_entries) if section_name == "الأفعال" else pattern_groups(all_entries)
            for group_index, group in enumerate(groups, 1):
                model = group["model"]
                ordinal += 1
                scope = " في " + group["label"] if section_name == "الأفعال" else ""
                _entry(document, model, ordinal, model_label=f"نموذج {group_index}{scope}")
                if group["members"]:
                    _paragraph(document, "على النمط نفسه في " + group["label"] if section_name == "الأفعال" else "على النمط نفسه", bold=True, keep=True, after=3)
                    for topic in TOPICS:
                        members = [entry for entry in group["members"] if entry["topic"] == topic]
                        if members:
                            _paragraph(document, topic, bold=True, keep=True, after=3)
                            ordinal = _compact_entries(document, members, ordinal, members=True)
            continue
        for t_index, topic in enumerate(t for t in TOPICS if t in sections[section_name]):
            _heading(document, topic, 2, f"topic_{s_index}_{t_index}", 1000+s_index*100+t_index)
            if not expanded:
                ordinal = _compact_entries(document, sections[section_name][topic], ordinal)
                continue
            for entry in sections[section_name][topic]:
                ordinal += 1
                _entry(document, entry, ordinal)
    p = _heading(document, "المراجع اللغوية", 1, "references", 9000)
    _paragraph(document, "المعاني والاستعمالات من مادة الكورس، مع استكمال التصريف والنبر من المراجع الآتية. البيانات المرجعية المستخدمة مرخصة بالمشاركة بالمثل مع نسب المصدر.", after=5)
    for source in lexicon.get("references", []):
        p = _paragraph(document, "", rtl=False, after=4)
        _link(p, source["name"], source["url"], internal=False, rtl=False)
        _run(p, "  " + source["license"], size=10)
    # Page numbers are useful in a long reference, without repeated page headers.
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    # Atomic replace keeps the last usable dictionary if Word has it locked.
    temporary = path.with_name(path.stem + ".tmp.docx")
    document.save(temporary)
    temporary.replace(path)
    return path
