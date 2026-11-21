"""Cumulative Word exports for the Russian course."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config.settings import settings
from app.exporters.common import clean_spacing, ensure_output_dir, study_text_key
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
    "الملابس والأغراض الشخصية",
    "الأماكن والمواصلات",
    "الطعام والشراب",
    "الزمن والتاريخ",
    "الطقس والطبيعة",
    "الجسم والصحة",
    "الثقافة والألعاب",
    "العلوم والتقنية",
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
        if should_exclude_vocabulary_entry(entry):
            continue
        entry["category"] = category_for_vocabulary_entry(entry)
        items.append(entry)
    return items


def russian_key(value: str) -> str:
    normalized = study_text_key(value)
    normalized = re.sub(r"[.!?…،؛:;]+$", "", normalized.strip())
    return re.sub(r"\s+", " ", normalized)


def _canonical_category_tokens(text: str) -> set[str]:
    """Tokenize a category label, stripping the definite article "ال".

    Whole-word matching against short family terms (أم/أب/أخ/أخت) needs this
    so "الأم" still matches "أم" as a word, while "أماكن" or "الأماكن"
    ("places") does not: that word merely starts with the letters "أم" as a
    substring, which is how it used to be mis-routed into "العائلة".
    """
    tokens = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
    return {
        token[2:] if token.startswith("ال") and len(token) > 3 else token
        for token in tokens
    }


def canonical_category(value: str) -> str:
    original = (value or "").strip()
    if original in CATEGORY_ORDER:
        return original
    text = original.casefold()
    tokens = _canonical_category_tokens(text)

    # Short family terms are matched as whole words only: checking them as a
    # substring (the old behaviour) makes any word that merely starts with
    # the same two letters as "أم" (e.g. "أماكن"/places) match "العائلة" by
    # accident.
    if tokens & {"أب", "أم", "أخ", "أخت"}:
        return "العائلة"

    # "صفات" and "وصف" contain "صف" but are not classroom labels.
    if tokens & {"صفة", "صفات", "وصف", "أوصاف", "لون", "ألوان"}:
        return "الصفات"
    if "صف" in tokens:
        return "الصف والتعليمات"

    mappings = (
        (("تحي", "وداع", "شكر", "ترحيب"), "التحيات والوداعات"),
        (("شخص", "مهن", "طالب", "طبيب", "اسم علم", "معلم", "أستاذ", "صديق"), "الأشخاص والمهن"),
        (("تعليم", "اقرأ", "اكتب", "درس"), "الصف والتعليمات"),
        (("ضمير", "إشارة", "ملكية"), "الضمائر وأسماء الإشارة"),
        (("سؤال", "جواب", "استفهام"), "الأسئلة والأجوبة"),
        (("عائل", "أسرة"), "العائلة"),
        (("بيت", "منزل", "أثاث", "غرفة"), "البيت والأثاث"),
        (("مكان", "أماكن", "مواصل", "مدينة", "جامعة", "مدرسة"), "الأماكن والمواصلات"),
        (("طعام", "شراب", "فاكه", "أكل"), "الطعام والشراب"),
        (("زمن", "وقت", "تاريخ", "يوم", "غد", "صباح"), "الزمن والتاريخ"),
        (("طقس", "طبيعة"), "الطقس والطبيعة"),
        (("عدد", "رقم", "كمية", "قياس"), "الأعداد والكميات"),
        (("فعل",), "الأفعال"),
        (("صفة",), "الصفات"),
        (("قاعد", "مصطلح", "نحو", "لغة", "حرف جر", "حرف عطف", "حرف"), "القواعد والمصطلحات"),
        (("عبار", "تعبير"), "عبارات عامة"),
    )
    if tokens & {"برد", "حر", "ثلج"}:
        return "الطقس والطبيعة"
    for keywords, category in mappings:
        if any(keyword in text for keyword in keywords):
            return category
    return "أخرى"


_NON_STUDY_VOCABULARY_KEYS = frozenset(
    russian_key(value)
    for value in (
        "Перерыв",
        "Отдохните",
        "Всё правильно",
        "Молодцы",
    )
)

_PRONOUN_VOCABULARY_KEYS = frozenset(
    russian_key(value)
    for value in (
        "Я",
        "Ты",
        "Он",
        "Она",
        "Оно",
        "Мы",
        "Вы",
        "Они",
        "Вам",
    )
)

_PEOPLE_VOCABULARY_KEYS = frozenset(
    russian_key(value)
    for value in (
        "Преподаватель",
        "Студент",
        "Друг",
    )
)

_GRAMMAR_VOCABULARY_KEYS = frozenset(
    russian_key(value)
    for value in (
        "Буква",
        "Большая",
        "Маленькая",
        "Но",
    )
)


def should_exclude_vocabulary_entry(entry: dict) -> bool:
    """Use the same filter for new extraction and previously stored rows."""
    # A user-reviewed legacy word is study material even when a generic
    # extraction filter would classify it as administrative classroom speech.
    if entry.get("study_role") == "legacy_study_word":
        return False
    key = russian_key(entry.get("russian", ""))
    if key in _NON_STUDY_VOCABULARY_KEYS or re.search(r"\bперерыв\b", key):
        return True
    if entry.get("study_role") == "sound_drill":
        return True
    context = study_text_key(" ".join(
        str(entry.get(field, "")) for field in ("category", "arabic", "english")
    ))
    return any(marker in context for marker in (
        "مقطع صوتي", "مقاطع صوتية", "مقطع تدريبي", "مقاطع تدريبية",
        "تدريب صوتي", "تدريب نطق بلا معنى", "practice word",
        "practice syllable", "sound drill", "meaningless syllable",
    ))


def category_for_vocabulary_entry(entry: dict) -> str:
    """Choose a stable topical category using all available semantics."""
    if russian_key(entry.get("russian", "")) in _PRONOUN_VOCABULARY_KEYS:
        return "الضمائر وأسماء الإشارة"
    if russian_key(entry.get("russian", "")) in _PEOPLE_VOCABULARY_KEYS:
        return "الأشخاص والمهن"
    if russian_key(entry.get("russian", "")) in _GRAMMAR_VOCABULARY_KEYS:
        return "القواعد والمصطلحات"
    explicit_category = entry.get("category", "")
    if explicit_category in CATEGORY_ORDER and explicit_category != "أخرى":
        return explicit_category
    context = " ".join(
        str(entry.get(field, ""))
        for field in ("category", "arabic", "english")
    )
    return canonical_category(context)


def _merge_text(old: str, new: str) -> str:
    # Split alternatives, not a slash inside a parenthetical explanation
    # such as "You (formal / plural)". Keep distinct meanings in order.
    parts = []
    seen = set()
    for value in (old, new):
        start = depth = 0
        for index, character in enumerate(value + "/"):
            if character in "([":
                depth += 1
            elif character in ")]":
                depth = max(0, depth - 1)
            if character == "/" and (depth == 0 or index == len(value)):
                part = value[start:index].strip()
                key = study_text_key(part)
                if key and key not in seen:
                    parts.append(part)
                    seen.add(key)
                start = index + 1
    return " / ".join(parts)


def remove_lecture_vocabulary(state: dict, lecture_number: int) -> None:
    """Drop one lecture's prior contribution from the vocabulary table.

    Re-running the same lecture must replace its rows, not merge a second
    copy of the same words on top of the ones an earlier attempt left
    behind. A word that also belongs to another lecture keeps its row, with
    just this lecture number removed from it.
    """
    remaining = []
    for entry in state["vocabulary"]:
        lectures = {
            int(value)
            for value in entry.get("lectures", [])
            if str(value).isdigit()
        }
        if lecture_number not in lectures:
            remaining.append(entry)
            continue
        lectures.discard(lecture_number)
        if lectures or entry.get("source_note"):
            entry["lectures"] = sorted(lectures)
            remaining.append(entry)
    state["vocabulary"] = remaining


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
            # A human-reviewed reading must not acquire an unreviewed,
            # conflicting transliteration when the word recurs next lesson.
            if field == "pronunciation" and current.get("pronunciation_reviewed"):
                continue
            current[field] = _merge_text(
                current.get(field, ""),
                new_entry.get(field, ""),
            )

    state["next_order"] = next_order


def normalize_vocabulary_state(state: dict) -> None:
    """Apply deterministic filtering and categorization to stored rows."""
    retained = []
    seen: dict[str, dict] = {}
    for entry in state.get("vocabulary", []):
        if should_exclude_vocabulary_entry(entry):
            continue
        for field in ("pronunciation", "arabic", "english"):
            if field in entry:
                entry[field] = _merge_text("", entry[field])
        entry["category"] = category_for_vocabulary_entry(entry)
        key = russian_key(entry.get("russian", ""))
        previous = seen.get(key)
        if previous is not None:
            previous["lectures"] = sorted({
                *previous.get("lectures", []), *entry.get("lectures", [])
            })
            for field in ("arabic", "english"):
                previous[field] = _merge_text(
                    previous.get(field, ""), entry.get(field, "")
                )
            if not previous.get("pronunciation_reviewed"):
                if entry.get("pronunciation_reviewed"):
                    previous["pronunciation"] = entry.get("pronunciation", "")
                    previous["pronunciation_reviewed"] = True
                else:
                    previous["pronunciation"] = _merge_text(
                        previous.get("pronunciation", ""),
                        entry.get("pronunciation", ""),
                    )
            continue
        seen[key] = entry
        retained.append(entry)
    state["vocabulary"] = retained


def prior_rule_names(
    state: dict,
    exclude_lecture_number: int | None = None,
) -> list[str]:
    names = []
    seen = set()
    lectures = sorted(
        (
            lecture
            for lecture in state.get("lectures", {}).values()
            if exclude_lecture_number is None
            or int(lecture.get("lecture_number", 0)) != exclude_lecture_number
        ),
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
    # Recent lessons are the ones the teacher is most likely to review.
    # Keeping only the first forty titles forgets all later grammar.
    return names[-40:]


def get_prior_rule_names(lecture_name: str | None = None) -> list[str]:
    """Return rule names from prior lectures, excluding `lecture_name` itself.

    Re-processing an already-stored lecture must not treat that lecture's
    own earlier attempt as a "previous lecture" whose rules now need only a
    one-line review; excluding it here keeps its rules explained in full.
    """
    state = load_state()
    exclude_lecture_number = None
    if lecture_name is not None:
        used_numbers = {
            int(value)
            for value in state.get("lectures", {})
            if str(value).isdigit()
        }
        exclude_lecture_number = lecture_number_from_name(
            lecture_name, used_numbers
        )
    return prior_rule_names(state, exclude_lecture_number=exclude_lecture_number)


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
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    title = document.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_direction(title, rtl=True)
    # Word's built-in Title style can add a colored bottom border.  Override
    # it on the paragraph so Arabic course exports use typography and spacing
    # for hierarchy without an unrelated decorative rule.
    properties = title._p.get_or_add_pPr()
    borders = properties.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        properties.append(borders)
    for edge_name in ("top", "left", "bottom", "right", "between", "bar"):
        edge = borders.find(qn(f"w:{edge_name}"))
        if edge is None:
            edge = OxmlElement(f"w:{edge_name}")
            borders.append(edge)
        edge.set(qn("w:val"), "nil")
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
    # NotebookLM often writes a subheading, its prose explanation and the
    # first Russian example on one physical line. Put every semantic tag on
    # its own line so Word can style the heading and each Russian card
    # independently instead of flattening the whole rule into one paragraph.
    tag_names = "|".join(tags)
    text = re.sub(
        rf"(?i)\s*(<(?:(?:{tag_names}))>)\s*",
        r"\n\1",
        text,
    )
    text = re.sub(
        rf"(?i)\s*(</(?:(?:{tag_names}))>)\s*",
        r"\1\n",
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
    title_text = (
        "ملخص كورس اللغة الروسية المحاضرة الأولى"
        if max_lecture == 1
        else f"ملخص كورس اللغة الروسية المحاضرات 1 إلى {max_lecture}"
    )
    _add_title(
        document,
        title_text,
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


def _keep_table_row_together(row) -> None:
    """Prevent a vocabulary entry from being split across pages."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = row._tr.get_or_add_trPr()
    if properties.find(qn("w:cantSplit")) is None:
        properties.append(OxmlElement("w:cantSplit"))


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
    """Default to the requested simple, reviewed table with lecture numbers.

    The optional lemma dictionaries and original extraction state stay intact.
    """
    from app.services.russian_flat_vocabulary import review_vocabulary
    from app.exporters.russian_flat_vocabulary import save_flat_document
    ensure_output_dir()
    review = review_vocabulary(state["vocabulary"])
    references = list(settings.OUTPUT_DIR.glob("جدول مفردات اللغة الروسية - المحاضرات 1-*.docx"))
    references = [p for p in references if re.search(r"1-\d+\.docx$", p.name)]
    if references:
        reference = max(references, key=lambda p:int(re.search(r"1-(\d+)\.docx$", p.name).group(1)))
        return save_flat_document(review, max_lecture, settings.OUTPUT_DIR, reference)
    reviewed_state = dict(state, vocabulary=[dict(r, russian=r["display_russian"]) for r in review["vocabulary"]])
    return save_legacy_vocabulary_document(reviewed_state, max_lecture, reviewed=True)


def save_legacy_vocabulary_document(state: dict, max_lecture: int, *, reviewed: bool = False) -> Path:
    from docx import Document
    from docx.shared import Cm

    path = settings.OUTPUT_DIR / (
        f"جدول مفردات اللغة الروسية - المحاضرات 1-{max_lecture}"
        + (" - مراجعة.docx" if reviewed else ".docx")
    )
    document = Document()
    _configure_document(document, landscape=True)
    title_text = (
        "جدول مفردات اللغة الروسية المحاضرة الأولى"
        if max_lecture == 1
        else f"جدول مفردات اللغة الروسية المحاضرات 1 إلى {max_lecture}"
    )
    _add_title(
        document,
        title_text,
        "يجمع الكلمات والعبارات الروسية مرة واحدة، مع اللفظ العربي "
        "والمعنى بالعربية والإنجليزية وأرقام المحاضرات. الكلمات المضافة "
        "من المرجع السابق مميزة بعبارة «الجدول القديم» لأن ترقيمه مختلف.",
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
        "المحاضرات / المصدر",
    )
    widths = (Cm(1.06), Cm(6.6), Cm(4.23), Cm(5.47), Cm(4.94), Cm(2.91))
    for index, width in enumerate(widths):
        table.columns[index].width = width
    header_row = table.rows[0]
    _set_repeat_table_header(header_row)
    _keep_table_row_together(header_row)
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
            _keep_table_row_together(category_row)
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
            merged.paragraphs[0].paragraph_format.keep_with_next = True
            current_category = category

        row_number += 1
        row = table.add_row()
        _keep_table_row_together(row)
        if row_number % 2 == 0:
            for cell in row.cells:
                _shade_cell(cell, "F5F9FC")
        lectures = " + ".join(
            str(number) for number in sorted(entry.get("lectures", []))
        )
        if not lectures:
            lectures = entry.get("source_note", "")
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
                rtl=index not in (0, 1, 4, 5),
                bold=index == 1,
                size=11.5 if index == 1 else (9.5 if index == 0 else 10.25),
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
    remove_lecture_vocabulary(state, lecture_number)
    merge_vocabulary(
        state,
        parse_vocabulary(vocabulary_text),
        lecture_number,
    )
    normalize_vocabulary_state(state)
    save_state(state)
    max_lecture = max(
        int(number) for number in state["lectures"]
    )
    summary_path = save_summary_document(state, max_lecture)
    vocabulary_path = save_vocabulary_document(state, max_lecture)
    return summary_path, vocabulary_path, lecture_number
