import re
from collections.abc import Callable

from app.config.settings import settings
from app.exporters.common import (
    ensure_output_dir,
    normalize_implicit_lists,
    repair_notebooklm_math_artifacts,
    safe_output_name,
    strip_repeated_heading,
)
from app.exporters.equations import linear_equation_to_omml
from app.utils.arabic import arabic_ordinal, number_main_heading
from app.utils.logger import logger


class WordExporter:
    @staticmethod
    def save(
        sections: list,
        lecture_name: str,
        clean_text: Callable[[str], str],
        date_provider: Callable[[], tuple[str, str, str]],
        number_main_headings: bool = True,
        document_title: str | None = None,
    ) -> None:
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
            from docx.oxml.shared import OxmlElement
            from docx.shared import Cm, Pt, RGBColor
        except ImportError:
            logger.error(
                "[bold red]python-docx is not installed. "
                "Run: pip install python-docx[/bold red]"
            )
            return

        def set_paragraph_direction(paragraph, *, rtl: bool) -> None:
            """Set Word paragraph direction explicitly for mixed documents."""
            paragraph_properties = paragraph._p.get_or_add_pPr()
            for existing in paragraph_properties.findall(qn("w:bidi")):
                paragraph_properties.remove(existing)

            bidi = OxmlElement("w:bidi")
            bidi.set(qn("w:val"), "1" if rtl else "0")
            paragraph_properties.append(bidi)

        def apply_rtl_and_size(
            paragraph,
            run,
            size_pt,
            is_bold=False,
            color_rgb=None,
            font_name=None,
        ):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            set_paragraph_direction(paragraph, rtl=True)

            run_properties = run._r.get_or_add_rPr()
            run_properties.append(OxmlElement("w:rtl"))

            if is_bold:
                run.bold = True
                run.font.cs_bold = True
                run_properties.append(OxmlElement("w:bCs"))
                run_properties.append(OxmlElement("w:b"))

            if color_rgb:
                run.font.color.rgb = color_rgb

            if font_name:
                run.font.name = font_name
                run_fonts = run_properties.find(qn("w:rFonts"))
                if run_fonts is None:
                    run_fonts = OxmlElement("w:rFonts")
                    run_properties.append(run_fonts)
                run_fonts.set(qn("w:ascii"), font_name)
                run_fonts.set(qn("w:hAnsi"), font_name)
                run_fonts.set(qn("w:cs"), font_name)

            run.font.size = Pt(size_pt)
            complex_size = OxmlElement("w:szCs")
            complex_size.set(qn("w:val"), str(int(size_pt * 2)))
            run_properties.append(complex_size)

        def apply_ltr_and_size(
            paragraph,
            run,
            size_pt,
            is_bold=False,
            color_rgb=None,
            font_name="Aptos",
        ):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            set_paragraph_direction(paragraph, rtl=False)
            run_properties = run._r.get_or_add_rPr()
            rtl = OxmlElement("w:rtl")
            rtl.set(qn("w:val"), "0")
            run_properties.append(rtl)

            run.font.name = font_name
            run_fonts = run_properties.find(qn("w:rFonts"))
            if run_fonts is None:
                run_fonts = OxmlElement("w:rFonts")
                run_properties.append(run_fonts)
            run_fonts.set(qn("w:ascii"), font_name)
            run_fonts.set(qn("w:hAnsi"), font_name)

            run.font.size = Pt(size_pt)
            if is_bold:
                run.bold = True
            if color_rgb:
                run.font.color.rgb = color_rgb

        def add_equation_paragraph(equation_text: str) -> None:
            """Insert a centered native Office Math paragraph."""
            paragraph = document.add_paragraph()
            if is_english_companion:
                set_paragraph_direction(paragraph, rtl=False)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)

            math_paragraph = OxmlElement("m:oMathPara")
            math_paragraph_properties = OxmlElement("m:oMathParaPr")
            justification = OxmlElement("m:jc")
            justification.set(qn("m:val"), "center")
            math_paragraph_properties.append(justification)
            math_paragraph.append(math_paragraph_properties)

            office_math = linear_equation_to_omml(equation_text)
            if office_math is None:
                office_math = OxmlElement("m:oMath")
                math_run = OxmlElement("m:r")
                math_run_properties = OxmlElement("m:rPr")
                math_style = OxmlElement("m:sty")
                math_style.set(qn("m:val"), "p")
                math_run_properties.append(math_style)
                math_run.append(math_run_properties)

                math_text = OxmlElement("m:t")
                math_text.set(qn("xml:space"), "preserve")
                math_text.text = equation_text.strip()
                math_run.append(math_text)
                office_math.append(math_run)
            math_paragraph.append(office_math)
            paragraph._p.append(math_paragraph)

        def add_inline_equation(paragraph, equation_text: str) -> None:
            office_math = linear_equation_to_omml(equation_text)
            if office_math is None:
                run = paragraph.add_run(equation_text.strip())
                apply_ltr_and_size(
                    paragraph,
                    run,
                    13,
                    font_name="Cambria Math",
                )
                return
            paragraph._p.append(office_math)

        ensure_output_dir()
        path = settings.OUTPUT_DIR / f"{safe_output_name(lecture_name)}.docx"
        document = Document()
        is_russian_course = any(
            "<russian>" in (text or "").casefold()
            for _, text in sections
        )
        is_english_companion = not number_main_headings

        for section in document.sections:
            section.top_margin = Cm(1.27)
            section.bottom_margin = Cm(1.27)
            section.left_margin = Cm(1.27)
            section.right_margin = Cm(1.27)

            footer_paragraph = section.footer.paragraphs[0]
            footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = footer_paragraph.add_run()
            field_begin = OxmlElement("w:fldChar")
            field_begin.set(qn("w:fldCharType"), "begin")
            instruction = OxmlElement("w:instrText")
            instruction.set(qn("xml:space"), "preserve")
            instruction.text = " PAGE "
            field_separator = OxmlElement("w:fldChar")
            field_separator.set(qn("w:fldCharType"), "separate")
            page_text = OxmlElement("w:t")
            page_text.text = "1"
            field_end = OxmlElement("w:fldChar")
            field_end.set(qn("w:fldCharType"), "end")
            run._r.extend(
                [
                    field_begin,
                    instruction,
                    field_separator,
                    page_text,
                    field_end,
                ]
            )

        if is_english_companion:
            for border in document.styles["Title"].element.xpath(".//w:pBdr"):
                border.getparent().remove(border)
            title = document.add_paragraph(style="Title")
            title_text = re.sub(r"[^\w\s]+", " ", document_title or lecture_name)
            title_run = title.add_run(re.sub(r"\s+", " ", title_text).strip())
            apply_rtl_and_size(title, title_run, 20, is_bold=True)
            title_run.font.color.rgb = RGBColor(0, 0, 0)

        if is_russian_course:
            title = document.add_paragraph(style="Title")
            title_text = re.sub(r"[^\w\s]+", " ", lecture_name)
            title_text = re.sub(r"\s+", " ", title_text).strip()
            title_run = title.add_run(
                f"تفريغ تعليمي لكورس اللغة الروسية {title_text}"
            )
            apply_rtl_and_size(title, title_run, 22, is_bold=True)
            title_run.font.color.rgb = RGBColor(0, 0, 0)

            subtitle = document.add_paragraph(style="Subtitle")
            subtitle_run = subtitle.add_run(
                "النص الروسي واللفظ بالعربية والمعنى"
            )
            apply_rtl_and_size(subtitle, subtitle_run, 14)
            subtitle_run.font.color.rgb = RGBColor(0, 0, 0)

            introduction = document.add_paragraph()
            introduction_run = introduction.add_run(
                "يرتب هذا الملف شرح المحاضرة بالتسلسل ويضع كل حرف أو كلمة "
                "روسية مع أقرب لفظ عربي ومعناها أو وظيفتها الصوتية."
            )
            apply_rtl_and_size(introduction, introduction_run, 13)

        table = document.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        table._tbl.tblPr.append(OxmlElement("w:bidiVisual"))

        day_name, hijri_date, gregorian_date = date_provider()
        headers = [
            day_name,
            hijri_date,
            gregorian_date,
            document_title or lecture_name,
        ]
        for index, cell in enumerate(table.rows[0].cells):
            paragraph = cell.paragraphs[0]
            run = paragraph.add_run(headers[index])
            apply_rtl_and_size(paragraph, run, 14, is_bold=True)

        document.add_paragraph()
        main_heading_number = 0
        question_number = 0

        for heading, text in sections:
            paragraph = document.add_paragraph(style="Heading 1")
            clean_heading = (
                heading.replace("[", "")
                .replace("]", "")
                .replace("**", "")
                .replace("#", "")
                .strip()
            )
            question_match = re.match(r"^سؤال\s*:\s*(.+)$", clean_heading)
            if question_match:
                if number_main_headings:
                    question_number += 1
                    question_ordinal = arabic_ordinal(
                        question_number,
                        definite=True,
                    )
                    formatted_heading = (
                        f"السؤال {question_ordinal}: "
                        f"{question_match.group(1).strip()}"
                    )
                else:
                    formatted_heading = clean_heading
            else:
                if number_main_headings:
                    main_heading_number += 1
                    formatted_heading = number_main_heading(
                        clean_heading,
                        main_heading_number,
                    )
                else:
                    formatted_heading = clean_heading

            run = paragraph.add_run(formatted_heading)
            apply_rtl_and_size(
                paragraph,
                run,
                16,
                is_bold=True,
                color_rgb=(
                    RGBColor(0, 0, 0) if not number_main_headings else None
                ),
            )

            text = strip_repeated_heading(text, clean_heading)
            if is_english_companion:
                text = re.sub(
                    r"\([A-Za-z][^()<>\r\n]*\)",
                    lambda match: match.group().replace(" ", "\u00a0"),
                    text,
                )
            text = repair_notebooklm_math_artifacts(text)
            text = normalize_implicit_lists(text)
            text = re.sub(r"\[[\s\d،,\-]+\]", "", text)
            text = re.sub(r"\n\s*\d+\s*\n\s*\.\s*", "\n", text)
            # NotebookLM sometimes collapses structural tags onto one line.
            # Restore the block boundaries needed for correct Word direction
            # and native equation rendering without changing the content.
            text = re.sub(
                r"(?i)</subheading>\s*<english>\s*",
                "</subheading>\n<english>\n",
                text,
            )
            text = re.sub(
                r"(?i)\s*</english>\s*<subheading>",
                "\n</english>\n<subheading>",
                text,
            )
            # Russian-course prompts use three line-scoped blocks. NotebookLM
            # can collapse adjacent tags, so restore one study row per line.
            for closing_tag, opening_tag in (
                ("subheading", "russian"),
                ("russian", "pronunciation"),
                ("pronunciation", "translation"),
                ("translation", "russian"),
                ("translation", "subheading"),
            ):
                text = re.sub(
                    rf"(?i)</{closing_tag}>\s*<{opening_tag}>",
                    f"</{closing_tag}>\n<{opening_tag}>",
                    text,
                )
            text = clean_text(text)
            lines = text.split("\n")

            in_quran = False
            in_hadith = False
            in_sanad = False
            in_matn = False
            in_highlight = False
            in_term = False
            in_scholar = False
            in_rule = False
            in_subheading = False
            in_english = False
            in_russian = False
            in_pronunciation = False
            in_translation = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.casefold() == "<english>":
                    in_english = True
                    continue
                if line.casefold() == "</english>":
                    in_english = False
                    continue
                if line.casefold() == "<russian>":
                    in_russian = True
                    continue
                if line.casefold() == "</russian>":
                    in_russian = False
                    continue
                if line.casefold() == "<pronunciation>":
                    in_pronunciation = True
                    continue
                if line.casefold() == "</pronunciation>":
                    in_pronunciation = False
                    continue
                if line.casefold() == "<translation>":
                    in_translation = True
                    continue
                if line.casefold() == "</translation>":
                    in_translation = False
                    continue
                if re.match(r"^[\d\s\.,:;!؟?()\[\]{}]+$", line):
                    continue
                if re.match(r"^[-_*]{3,}$", line):
                    continue

                chatter_keywords = [
                    "إليك التفريغ",
                    "إليك تفريغ",
                    "الفقرة المطلوبة",
                    "مصاغاً بلفظي",
                    "مصاغا بلفظي",
                    "مصاغةً بلسان",
                    "كأنني أنا الشارح",
                    "المنهجية التي طلبتها",
                    "دون أي اختصار:",
                    "بجميع تفاصيلها ومناقشاتها",
                    "بجميع تفاصيلها واستطراداتها",
                    "مع الالتزام التام بتعليمات",
                    "التزاماً بالتعليمات",
                    "خلت هذه الفقرة من",
                    "تنبيه: خلت هذه",
                    "وقد تم وضع النص المقروء",
                    "وقد تم تمييز النص",
                ]
                if (
                    any(keyword in line for keyword in chatter_keywords)
                    and len(line) < 300
                ):
                    continue

                line_clean = (
                    line.replace("[", "")
                    .replace("]", "")
                    .replace("**", "")
                    .replace("#", "")
                    .strip()
                )
                if line_clean == clean_heading or (
                    clean_heading in line_clean
                    and len(line_clean) < len(clean_heading) + 10
                ):
                    continue

                equation_match = re.fullmatch(
                    r"(?:[-*•]\s*)?<equation>\s*(.+?)\s*</equation>",
                    line,
                    flags=re.IGNORECASE,
                )
                if equation_match:
                    add_equation_paragraph(equation_match.group(1))
                    continue

                if line.startswith("[") and line.endswith("]"):
                    heading_words = set(clean_heading.split())
                    line_words = set(line_clean.split())
                    if heading_words and line_words:
                        overlap = len(heading_words & line_words)
                        similarity = overlap / max(len(heading_words), 1)
                        if (
                            similarity > 0.5
                            and len(line_clean) < len(clean_heading) + 50
                        ):
                            continue

                is_subheading = line.startswith("#")
                is_bullet = False
                is_number = False
                if not is_subheading:
                    if re.match(r"^(?:[-*•●◦▪])\s+", line):
                        is_bullet = True
                        line = re.sub(r"^(?:[-*•●◦▪])\s+", "", line)
                        line_clean = re.sub(
                            r"^(?:[-*•●◦▪])\s+",
                            "",
                            line_clean,
                        )
                    elif re.match(r"^\d+[\.)]\s+", line):
                        is_number = True
                        line = re.sub(r"^\d+[\.)]\s+", "", line)
                        line_clean = re.sub(
                            r"^\d+[\.)]\s+",
                            "",
                            line_clean,
                        )

                if is_bullet:
                    paragraph = document.add_paragraph(style="List Bullet")
                elif is_number:
                    paragraph = document.add_paragraph(style="List Number")
                else:
                    paragraph = document.add_paragraph()

                # Keep every Russian study card together across page breaks:
                # the source line stays with its Arabic pronunciation, and the
                # pronunciation stays with the Arabic meaning.
                normalized_line = line.lstrip().casefold()
                if not number_main_headings and (
                    in_english or normalized_line.startswith("المعنى:")
                ):
                    paragraph.paragraph_format.keep_with_next = True
                if (
                    "<russian>" in normalized_line
                    or normalized_line.startswith("<pronunciation>")
                ):
                    paragraph.paragraph_format.keep_with_next = True
                if re.fullmatch(
                    r"<subheading>[^<]+</subheading>",
                    line.strip(),
                    flags=re.IGNORECASE,
                ):
                    paragraph.paragraph_format.keep_with_next = True

                if is_subheading:
                    paragraph.style = "Heading 2"
                    run = paragraph.add_run(line_clean)
                    apply_rtl_and_size(
                        paragraph,
                        run,
                        16,
                        is_bold=True,
                        color_rgb=(
                            RGBColor(0, 0, 0)
                            if not number_main_headings
                            else None
                        ),
                    )
                    continue

                parts = re.split(
                    r"(<equation>[^\r\n]*?</equation>|"
                    r"</?quran>|</?hadith>|</?sanad>|</?matn>|"
                    r"</?highlight>|</?subheading>|"
                    r"</?term>|</?scholar>|</?rule>|"
                    r"</?english>|"
                    r"</?russian>|</?pronunciation>|</?translation>|"
                    r"\*\*.*?\*\*)",
                    line,
                    flags=re.IGNORECASE,
                )
                for part in parts:
                    if not part:
                        continue
                    inline_equation_match = re.fullmatch(
                        r"<equation>\s*(.*?)\s*</equation>",
                        part,
                        flags=re.IGNORECASE,
                    )
                    if inline_equation_match:
                        add_inline_equation(
                            paragraph,
                            inline_equation_match.group(1),
                        )
                        continue
                    if part == "<quran>":
                        in_quran = True
                        run = paragraph.add_run("﴿")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            is_bold=True,
                            color_rgb=RGBColor(0, 128, 0),
                            font_name="Traditional Arabic",
                        )
                        continue
                    if part == "</quran>":
                        in_quran = False
                        run = paragraph.add_run("﴾")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            is_bold=True,
                            color_rgb=RGBColor(0, 128, 0),
                            font_name="Traditional Arabic",
                        )
                        continue
                    if part == "<hadith>":
                        in_hadith = True
                        run = paragraph.add_run("«")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            color_rgb=RGBColor(0, 0, 255),
                        )
                        continue
                    if part == "</hadith>":
                        in_hadith = False
                        run = paragraph.add_run("»")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            color_rgb=RGBColor(0, 0, 255),
                        )
                        continue
                    if part == "<sanad>":
                        in_sanad = True
                        continue
                    if part == "</sanad>":
                        in_sanad = False
                        continue
                    if part == "<matn>":
                        in_matn = True
                        run = paragraph.add_run("[")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            is_bold=True,
                            color_rgb=RGBColor(128, 0, 128),
                        )
                        continue
                    if part == "</matn>":
                        in_matn = False
                        run = paragraph.add_run("]")
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            16,
                            is_bold=True,
                            color_rgb=RGBColor(128, 0, 128),
                        )
                        continue
                    if part == "<highlight>":
                        in_highlight = True
                        continue
                    if part == "</highlight>":
                        in_highlight = False
                        continue
                    if part == "<subheading>":
                        in_subheading = True
                        continue
                    if part == "</subheading>":
                        in_subheading = False
                        continue
                    if part == "<term>":
                        in_term = True
                        continue
                    if part == "</term>":
                        in_term = False
                        continue
                    if part == "<scholar>":
                        in_scholar = True
                        continue
                    if part == "</scholar>":
                        in_scholar = False
                        continue
                    if part == "<rule>":
                        in_rule = True
                        continue
                    if part == "</rule>":
                        in_rule = False
                        continue
                    if part == "<english>":
                        in_english = True
                        continue
                    if part == "</english>":
                        in_english = False
                        continue
                    if part == "<russian>":
                        in_russian = True
                        continue
                    if part == "</russian>":
                        in_russian = False
                        continue
                    if part == "<pronunciation>":
                        in_pronunciation = True
                        continue
                    if part == "</pronunciation>":
                        in_pronunciation = False
                        continue
                    if part == "<translation>":
                        in_translation = True
                        continue
                    if part == "</translation>":
                        in_translation = False
                        continue

                    is_bold = False
                    if part.startswith("**") and part.endswith("**"):
                        part = part[2:-2]
                        is_bold = True

                    color = None
                    font_name = None
                    if in_quran:
                        color = RGBColor(0, 128, 0)
                        font_name = "Traditional Arabic"
                        is_bold = True
                    elif in_hadith:
                        color = RGBColor(0, 0, 255)
                    elif in_sanad:
                        color = RGBColor(128, 0, 0)
                    elif in_matn or in_highlight:
                        color = RGBColor(128, 0, 128)
                        is_bold = True
                    elif in_subheading:
                        color = RGBColor(0, 0, 0) if is_english_companion else RGBColor(192, 0, 0)
                        is_bold = True
                    elif in_rule:
                        color = RGBColor(0, 139, 139)
                        is_bold = True
                    elif in_pronunciation:
                        color = RGBColor(0, 128, 96)
                    elif in_translation:
                        color = RGBColor(31, 78, 121)

                    # Keep English terms and time ranges internally LTR while
                    # retaining the surrounding Arabic paragraph direction.
                    if is_english_companion and not (in_english or in_russian):
                        chunks = re.split(
                            r"(\([^()\u0600-\u06ff]*[A-Za-z][^()\u0600-\u06ff]*\)|"
                            r"\d{1,2}:\d{2}(?::\d{2})?(?:[–−-]\d{1,2}:\d{2})?)",
                            part,
                        )
                        for chunk in chunks:
                            if not chunk:
                                continue
                            run = paragraph.add_run(chunk)
                            apply_rtl_and_size(
                                paragraph, run,
                                15 if (in_pronunciation or in_translation) else 14,
                                is_bold=is_bold, color_rgb=color,
                                font_name=font_name,
                            )
                            if re.fullmatch(
                                r"\([^()\u0600-\u06ff]*[A-Za-z][^()\u0600-\u06ff]*\)|"
                                r"\d{1,2}:\d{2}(?::\d{2})?(?:[–−-]\d{1,2}:\d{2})?",
                                chunk,
                            ):
                                # Digits and separators otherwise inherit the
                                # Arabic bidi context in Word/LibreOffice.
                                run.text = "\u200e" + chunk + "\u200e"
                                run._r.get_or_add_rPr().find(qn("w:rtl")).set(qn("w:val"), "0")
                        continue

                    run = paragraph.add_run(part)
                    if in_english or in_russian:
                        apply_ltr_and_size(
                            paragraph,
                            run,
                            15 if in_russian else 13,
                            is_bold=is_bold or in_russian,
                            color_rgb=(
                                RGBColor(112, 48, 160)
                                if in_russian and color is None
                                else color
                            ),
                        )
                    else:
                        apply_rtl_and_size(
                            paragraph,
                            run,
                            15 if (in_pronunciation or in_translation)
                            else (14 if is_english_companion else 16),
                            is_bold=is_bold,
                            color_rgb=color,
                            font_name=font_name,
                        )

            document.add_paragraph()

        document.save(path)
        logger.info(
            f"[bold green]Saved Word Document to {path}[/bold green]"
        )
