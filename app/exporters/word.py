import re
from collections.abc import Callable

from app.config.settings import settings
from app.exporters.common import (
    ensure_output_dir,
    normalize_implicit_lists,
    safe_output_name,
    strip_repeated_heading,
)
from app.utils.arabic import arabic_ordinal, number_main_heading
from app.utils.logger import logger


class WordExporter:
    @staticmethod
    def save(
        sections: list,
        lecture_name: str,
        clean_text: Callable[[str], str],
        date_provider: Callable[[], tuple[str, str, str]],
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

        def apply_rtl_and_size(
            paragraph,
            run,
            size_pt,
            is_bold=False,
            color_rgb=None,
            font_name=None,
        ):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph_properties = paragraph._p.get_or_add_pPr()
            paragraph_properties.append(OxmlElement("w:bidi"))

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

        ensure_output_dir()
        path = settings.OUTPUT_DIR / f"{safe_output_name(lecture_name)}.docx"
        document = Document()

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

        table = document.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        table._tbl.tblPr.append(OxmlElement("w:bidiVisual"))

        day_name, hijri_date, gregorian_date = date_provider()
        headers = [
            day_name,
            hijri_date,
            gregorian_date,
            lecture_name,
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
                main_heading_number += 1
                formatted_heading = number_main_heading(
                    clean_heading,
                    main_heading_number,
                )

            run = paragraph.add_run(formatted_heading)
            apply_rtl_and_size(paragraph, run, 16, is_bold=True)

            text = strip_repeated_heading(text, clean_heading)
            text = normalize_implicit_lists(text)
            text = re.sub(r"\[[\s\d،,\-]+\]", "", text)
            text = re.sub(r"\n\s*\d+\s*\n\s*\.\s*", "\n", text)
            lines = clean_text(text).split("\n")

            in_quran = False
            in_hadith = False
            in_sanad = False
            in_matn = False
            in_highlight = False
            in_term = False
            in_scholar = False
            in_rule = False

            for line in lines:
                line = line.strip()
                if not line:
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

                if is_subheading:
                    paragraph.style = "Heading 2"
                    run = paragraph.add_run(line_clean)
                    apply_rtl_and_size(paragraph, run, 16, is_bold=True)
                    continue

                parts = re.split(
                    r"(</?quran>|</?hadith>|</?sanad>|</?matn>|"
                    r"</?highlight>|</?term>|</?scholar>|</?rule>|"
                    r"\*\*.*?\*\*)",
                    line,
                )
                for part in parts:
                    if not part:
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
                    elif in_rule:
                        color = RGBColor(0, 139, 139)
                        is_bold = True

                    run = paragraph.add_run(part)
                    apply_rtl_and_size(
                        paragraph,
                        run,
                        16,
                        is_bold=is_bold,
                        color_rgb=color,
                        font_name=font_name,
                    )

            document.add_paragraph()

        document.save(path)
        logger.info(
            f"[bold green]Saved Word Document to {path}[/bold green]"
        )
