"""Cumulative Word exports for the Russian course."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app.config.settings import settings
from app.exporters.common import clean_spacing, ensure_output_dir
from app.utils.logger import logger


STATE_FILENAME = ".russian_course_cumulative.json"

CATEGORY_ORDER = (
    "التحيات والوداعات",
    "الصف والتعليمات",
    "الضمائر وأسماء الإشارة",
    "الأسئلة والأجوبة",
    "العائلة",
    "الأشخاص والمهن",
    "البيت والأثاث",
    "الأماكن والمواصلات",
    "الطعام والشراب",
    "الزمن والتاريخ",
    "الطقس والطبيعة",
    "الأعداد والكميات",
    "الأفعال",
    "الصفات",
    "القواعد والمصطلحات",
    "عبارات عامة",
    "أخرى",
)

LECTURE_LABELS = {
    1: "الأولى",
    2: "الثانية",
    3: "الثالثة",
    4: "الرابعة",
    5: "الخامسة",
    6: "السادسة",
    7: "السابعة",
    8: "الثامنة",
    9: "التاسعة",
    10: "العاشرة",
}


def _default_state() -> dict:
    return {
        "version": 1,
        "lectures": {},
        "vocabulary": [],
        "next_order": 1,
    }


def _state_path() -> Path:
    return settings.OUTPUT_DIR / STATE_FILENAME


def load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return _default_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "[bold yellow]Could not read the cumulative Russian state; "
            "a new state will be used.[/bold yellow]"
        )
        return _default_state()
    default = _default_state()
    for key, value in default.items():
        state.setdefault(key, value)
    return state


def save_state(state: dict) -> None:
    ensure_output_dir()
    path = _state_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def lecture_number_from_name(
    lecture_name: str,
    used_numbers: set[int] | None = None,
) -> int:
    used_numbers = used_numbers or set()
    leading = re.match(r"\s*([0-9٠-٩]+)", lecture_name)
    if leading:
        translated = leading.group(1).translate(
            str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        )
        number = int(translated)
        if number > 0:
            return number

    for number, label in LECTURE_LABELS.items():
        if label in lecture_name:
            return number

    return max(used_numbers, default=0) + 1


def _tag_value(block: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}>\s*(.*?)\s*</{tag}>",
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return clean_spacing(match.group(1)).strip()


def parse_vocabulary(text: str) -> list[dict]:
    items = []
    blocks = re.findall(
        r"<vocabulary_item>\s*(.*?)\s*</vocabulary_item>",
        text or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in blocks:
        entry = {
            "category": _tag_value(block, "category"),
            "russian": _tag_value(block, "russian"),
            "pronunciation": _tag_value(block, "pronunciation"),
            "arabic": _tag_value(block, "translation"),
            "english": _tag_value(block, "english"),
        }
        if not all(
            entry[field]
            for field in ("russian", "pronunciation", "arabic", "english")
        ):
            continue
        if not re.search(r"[А-Яа-яЁё]", entry["russian"]):
            continue
        combined = f'{entry["category"]} {entry["arabic"]}'.casefold()
        if any(
            marker in combined
            for marker in (
                "مقطع صوتي",
                "مقاطع صوتية",
                "تدريب صوتي",
                "تدريب نطق بلا معنى",
            )
        ):
            continue
        entry["category"] = canonical_category(entry["category"])
        items.append(entry)
    return items


def russian_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = re.sub(r"[.!?…،؛:;]+$", "", normalized.strip())
    return re.sub(r"\s+", " ", normalized)


def canonical_category(value: str) -> str:
    text = (value or "").strip().casefold()
    mappings = (
        (("تحي", "وداع", "شكر", "ترحيب"), "التحيات والوداعات"),
        (("صف", "تعليم", "اقرأ", "اكتب", "معلم", "درس"), "الصف والتعليمات"),
        (("ضمير", "إشارة", "ملكية"), "الضمائر وأسماء الإشارة"),
        (("سؤال", "جواب", "استفهام"), "الأسئلة والأجوبة"),
        (("عائل", "أسرة", "أب", "أم", "أخ", "أخت"), "العائلة"),
        (("شخص", "مهن", "طالب", "طبيب", "اسم علم"), "الأشخاص والمهن"),
        (("بيت", "منزل", "أثاث", "غرفة"), "البيت والأثاث"),
        (("مكان", "مواصل", "مدينة", "جامعة", "مدرسة"), "الأماكن والمواصلات"),
        (("طعام", "شراب", "فاكه", "أكل"), "الطعام والشراب"),
        (("زمن", "وقت", "تاريخ", "يوم", "غد", "صباح"), "الزمن والتاريخ"),
        (("طقس", "طبيعة", "برد", "حر", "ثلج"), "الطقس والطبيعة"),
        (("عدد", "رقم", "كمية", "قياس"), "الأعداد والكميات"),
        (("فعل",), "الأفعال"),
        (("صفة",), "الصفات"),
        (("قاعد", "مصطلح", "نحو", "لغة"), "القواعد والمصطلحات"),
        (("عبار", "تعبير"), "عبارات عامة"),
    )
    for keywords, category in mappings:
        if any(keyword in text for keyword in keywords):
            return category
    return "أخرى"


def _merge_text(old: str, new: str) -> str:
    old = old.strip()
    new = new.strip()
    if not old:
        return new
    if not new or new.casefold() in old.casefold():
        return old
    if old.casefold() in new.casefold():
        return new
    return f"{old} / {new}"


def merge_vocabulary(
    state: dict,
    new_entries: list[dict],
    lecture_number: int,
) -> None:
    existing = {
        russian_key(entry.get("russian", "")): entry
        for entry in state["vocabulary"]
        if entry.get("russian")
    }
    next_order = int(state.get("next_order", 1))

    for new_entry in new_entries:
        key = russian_key(new_entry["russian"])
        if not key:
            continue
        current = existing.get(key)
        if current is None:
            current = {
                **new_entry,
                "lectures": [lecture_number],
                "order": next_order,
            }
            next_order += 1
            state["vocabulary"].append(current)
            existing[key] = current
            continue

        lectures = {
            int(value)
            for value in current.get("lectures", [])
            if str(value).isdigit()
        }
        lectures.add(lecture_number)
        current["lectures"] = sorted(lectures)
        for field in ("pronunciation", "arabic", "english"):
            current[field] = _merge_text(
                current.get(field, ""),
                new_entry.get(field, ""),
            )

    state["next_order"] = next_order


def prior_rule_names(state: dict) -> list[str]:
    names = []
    seen = set()
    lectures = sorted(
        state.get("lectures", {}).values(),
        key=lambda item: int(item.get("lecture_number", 0)),
    )
    for lecture in lectures:
        for section in lecture.get("sections", []):
            if section.get("heading") != "القواعد والتطبيقات":
                continue
            for name in re.findall(
                r"<subheading>\s*(.*?)\s*</subheading>",
                section.get("text", ""),
                flags=re.IGNORECASE | re.DOTALL,
            ):
                cleaned = clean_spacing(name).strip()
                key = cleaned.casefold()
                if (
                    cleaned
                    and key not in seen
                    and cleaned != "القواعد والتطبيقات"
                ):
                    seen.add(key)
                    names.append(cleaned)
    return names[:40]


def get_prior_rule_names() -> list[str]:
    return prior_rule_names(load_state())


def _set_direction(paragraph, *, rtl: bool) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph_properties = paragraph._p.get_or_add_pPr()
    for existing in paragraph_properties.findall(qn("w:bidi")):
        paragraph_properties.remove(existing)
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1" if rtl else "0")
    paragraph_properties.append(bidi)


def _format_run(
    paragraph,
    run,
    *,
    size: float,
    rtl: bool,
    bold: bool = False,
    color: str = "000000",
    font_name: str = "Arial",
) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
    )
    _set_direction(paragraph, rtl=rtl)
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    run_properties = run._r.get_or_add_rPr()
    run_fonts = run_properties.find(qn("w:rFonts"))
    if run_fonts is None:
        run_fonts = OxmlElement("w:rFonts")
        run_properties.append(run_fonts)
    for attribute in ("ascii", "hAnsi", "cs", "eastAsia"):
        run_fonts.set(qn(f"w:{attribute}"), font_name)
    rtl_element = OxmlElement("w:rtl")
    rtl_element.set(qn("w:val"), "1" if rtl else "0")
    run_properties.append(rtl_element)


def _add_page_number(section) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separator = OxmlElement("w:fldChar")
    separator.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instruction, separator, text, end])


def _configure_document(document, *, landscape: bool = False) -> None:
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm

    for section in document.sections:
        if landscape:
            section.orientation = WD_ORIENT.LANDSCAPE
            section.page_width, section.page_height = (
                section.page_height,
                section.page_width,
            )
        section.top_margin = Cm(1.3)
        section.bottom_margin = Cm(1.3)
        section.left_margin = Cm(1.2)
        section.right_margin = Cm(1.2)
        _add_page_number(section)


def _add_title(document, title_text: str, introduction: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    title = document.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_direction(title, rtl=True)
    title.paragraph_format.space_after = Pt(8)
    run = title.add_run(title_text)
    _format_run(title, run, size=22, rtl=True, bold=True)

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(12)
    run = paragraph.add_run(introduction)
    _format_run(paragraph, run, size=12.5, rtl=True)


def _normalize_summary_lines(text: str) -> list[str]:
    text = clean_spacing(text or "")
    tags = (
        "subheading",
        "speaker",
        "russian",
        "pronunciation",
        "translation",
        "highlight",
    )
    for closing in tags:
        for opening in tags:
            text = re.sub(
                rf"(?i)</{closing}>\s*<{opening}>",
                f"</{closing}>\n<{opening}>",
                text,
            )
    return [line.strip() for line in text.splitlines() if line.strip()]


def _add_summary_content(document, text: str, section_heading: str) -> None:
    from docx.shared import Pt

    for line in _normalize_summary_lines(text):
        full_tag = re.fullmatch(
            r"<(subheading|speaker|russian|pronunciation|translation|highlight)>"
            r"\s*(.*?)\s*</\1>",
            line,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if full_tag:
            tag = full_tag.group(1).casefold()
            value = full_tag.group(2).strip()
            if not value:
                continue
            if tag == "subheading":
                if value.casefold() == section_heading.casefold():
                    continue
                paragraph = document.add_paragraph(style="Heading 3")
                paragraph.paragraph_format.keep_with_next = True
                run = paragraph.add_run(value)
                _format_run(
                    paragraph,
                    run,
                    size=13.5,
                    rtl=True,
                    bold=True,
                )
            elif tag == "speaker":
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.keep_with_next = True
                run = paragraph.add_run(f"المتحدث {value}")
                _format_run(
                    paragraph,
                    run,
                    size=11.5,
                    rtl=True,
                    bold=True,
                    color="7030A0",
                )
            elif tag == "russian":
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.keep_with_next = True
                run = paragraph.add_run(value)
                _format_run(
                    paragraph,
                    run,
                    size=14,
                    rtl=False,
                    bold=True,
                    color="7030A0",
                )
            elif tag == "pronunciation":
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.keep_with_next = True
                run = paragraph.add_run(f"اللفظ بالعربية: {value}")
                _format_run(
                    paragraph,
                    run,
                    size=12.5,
                    rtl=True,
                    color="008060",
                )
            elif tag == "translation":
                paragraph = document.add_paragraph()
                run = paragraph.add_run(f"المعنى بالعربية: {value}")
                _format_run(
                    paragraph,
                    run,
                    size=12.5,
                    rtl=True,
                    color="1F4E79",
                )
            else:
                paragraph = document.add_paragraph()
                run = paragraph.add_run(value)
                _format_run(
                    paragraph,
                    run,
                    size=12.5,
                    rtl=True,
                    bold=True,
                    color="800080",
                )
            continue

        is_bullet = bool(re.match(r"^(?:[-*•●◦▪])\s+", line))
        line = re.sub(r"^(?:[-*•●◦▪])\s+", "", line)
        line = re.sub(r"</?[a-z_]+(?:\s+[^>]*)?>", "", line, flags=re.I)
        line = line.replace("**", "").replace("#", "").strip()
        if not line:
            continue
        paragraph = document.add_paragraph(
            style="List Bullet" if is_bullet else None
        )
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(line)
        _format_run(paragraph, run, size=12.5, rtl=True)


def save_summary_document(state: dict, max_lecture: int) -> Path:
    from docx import Document
    from docx.shared import Pt

    path = settings.OUTPUT_DIR / (
        f"ملخص كورس اللغة الروسية - المحاضرات 1-{max_lecture}.docx"
    )
    document = Document()
    _configure_document(document)
    _add_title(
        document,
        f"ملخص كورس اللغة الروسية المحاضرات 1 إلى {max_lecture}",
        "ملخص تراكمي مرتب للحروف والقواعد والحوارات والخلاصة والواجب. "
        "توجد المفردات الكاملة في جدول منفصل.",
    )

    lectures = sorted(
        state["lectures"].values(),
        key=lambda item: int(item["lecture_number"]),
    )
    for index, lecture in enumerate(lectures):
        if index:
            document.add_page_break()
        number = int(lecture["lecture_number"])
        label = LECTURE_LABELS.get(number, str(number))
        heading = document.add_paragraph(style="Heading 1")
        heading.paragraph_format.space_before = Pt(6)
        heading.paragraph_format.space_after = Pt(8)
        run = heading.add_run(f"المحاضرة {label}")
        _format_run(heading, run, size=18, rtl=True, bold=True)

        source = document.add_paragraph()
        source_run = source.add_run(f"المصدر: {lecture['source_name']}")
        _format_run(source, source_run, size=10.5, rtl=True, color="666666")

        for section in lecture.get("sections", []):
            section_heading = section["heading"]
            paragraph = document.add_paragraph(style="Heading 2")
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(5)
            run = paragraph.add_run(section_heading)
            _format_run(paragraph, run, size=15, rtl=True, bold=True)
            _add_summary_content(
                document,
                section.get("text", ""),
                section_heading,
            )

    document.save(path)
    logger.info(
        f"[bold green]Saved cumulative Russian summary to {path}[/bold green]"
    )
    return path


def _shade_cell(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _set_cell_margins(cell, value: int = 90) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for edge in ("top", "left", "bottom", "right"):
        element = margins.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def _set_repeat_table_header(row) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    properties.append(header)


def _set_cell_text(
    cell,
    value: str,
    *,
    rtl: bool,
    bold: bool = False,
    color: str = "000000",
    size: float = 10.5,
) -> None:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell)
    paragraph = cell.paragraphs[0]
    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.CENTER
    )
    run = paragraph.add_run(value)
    _format_run(
        paragraph,
        run,
        size=size,
        rtl=rtl,
        bold=bold,
        color=color,
    )


def save_vocabulary_document(state: dict, max_lecture: int) -> Path:
    from docx import Document
    from docx.shared import Cm

    path = settings.OUTPUT_DIR / (
        f"جدول مفردات اللغة الروسية - المحاضرات 1-{max_lecture}.docx"
    )
    document = Document()
    _configure_document(document, landscape=True)
    _add_title(
        document,
        f"جدول مفردات اللغة الروسية المحاضرات 1 إلى {max_lecture}",
        "يجمع الكلمات والعبارات الروسية مرة واحدة، مع اللفظ العربي "
        "والمعنى بالعربية والإنجليزية وأرقام المحاضرات.",
    )

    table = document.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.autofit = False
    headers = (
        "م",
        "الكلمة أو العبارة الروسية",
        "اللفظ بالعربية",
        "المعنى بالعربية",
        "English meaning",
        "المحاضرات",
    )
    widths = (Cm(1), Cm(5.5), Cm(4.5), Cm(6), Cm(5.5), Cm(2.4))
    header_row = table.rows[0]
    _set_repeat_table_header(header_row)
    for index, cell in enumerate(header_row.cells):
        cell.width = widths[index]
        _shade_cell(cell, "1F4E79")
        _set_cell_text(
            cell,
            headers[index],
            rtl=index != 4,
            bold=True,
            color="FFFFFF",
            size=10.5,
        )

    category_rank = {
        category: index for index, category in enumerate(CATEGORY_ORDER)
    }
    entries = sorted(
        state["vocabulary"],
        key=lambda item: (
            category_rank.get(item.get("category", "أخرى"), 999),
            int(item.get("order", 0)),
        ),
    )
    current_category = None
    row_number = 0
    for entry in entries:
        category = canonical_category(entry.get("category", ""))
        if category != current_category:
            category_row = table.add_row()
            merged = category_row.cells[0]
            for cell in category_row.cells[1:]:
                merged = merged.merge(cell)
            _shade_cell(merged, "D9EAF7")
            _set_cell_text(
                merged,
                category,
                rtl=True,
                bold=True,
                size=11,
            )
            current_category = category

        row_number += 1
        row = table.add_row()
        if row_number % 2 == 0:
            for cell in row.cells:
                _shade_cell(cell, "F5F9FC")
        lectures = " + ".join(
            str(number) for number in sorted(entry.get("lectures", []))
        )
        values = (
            str(row_number),
            entry.get("russian", ""),
            entry.get("pronunciation", ""),
            entry.get("arabic", ""),
            entry.get("english", ""),
            lectures,
        )
        for index, cell in enumerate(row.cells):
            cell.width = widths[index]
            _set_cell_text(
                cell,
                values[index],
                rtl=index not in (1, 4),
                bold=index == 1,
                size=10.25,
            )

    document.save(path)
    logger.info(
        f"[bold green]Saved cumulative Russian vocabulary to {path}[/bold green]"
    )
    return path


def update_cumulative_outputs(
    lecture_name: str,
    summary_sections: list[tuple[str, str]],
    vocabulary_text: str,
) -> tuple[Path, Path, int]:
    """Replace one lecture in state and regenerate both cumulative documents."""
    ensure_output_dir()
    state = load_state()
    used_numbers = {
        int(value)
        for value in state.get("lectures", {})
        if str(value).isdigit()
    }
    lecture_number = lecture_number_from_name(lecture_name, used_numbers)
    state["lectures"][str(lecture_number)] = {
        "lecture_number": lecture_number,
        "source_name": lecture_name,
        "sections": [
            {"heading": heading, "text": text}
            for heading, text in summary_sections
        ],
    }
    merge_vocabulary(
        state,
        parse_vocabulary(vocabulary_text),
        lecture_number,
    )
    save_state(state)
    max_lecture = max(
        int(number) for number in state["lectures"]
    )
    summary_path = save_summary_document(state, max_lecture)
    vocabulary_path = save_vocabulary_document(state, max_lecture)
    return summary_path, vocabulary_path, lecture_number
