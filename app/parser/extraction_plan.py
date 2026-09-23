import re

from app.models.schemas import ExtractionItem
from app.utils.arabic import number_main_heading, strip_main_heading_ordinal
from app.utils.logger import logger


class ExtractionPlanParser:
    """Parse extraction items from NotebookLM's phase-one response."""

    MAIN_HEADING_PATTERN = re.compile(
        r"\[\[\s*(?:رئيسي|عنوان\s+رئيسي|main)\s*[:：\-]\s*"
        r"([^\]\r\n]+?)\s*\]\]"
    )
    END_EXPLANATION_PATTERN = re.compile(
        r"\[\[\s*(?:نهاية\s+الشرح|انتهاء\s+الشرح|"
        r"end\s+of\s+explanation)\s*\]\]"
    )
    END_QUESTION_PATTERN = re.compile(
        r"\[\[\s*(?:سؤال\s+ختامي|سؤال\s+نهاية\s+الدرس|end\s+question)"
        r"\s*[:：\-]\s*([^\]\r\n]+?)\s*\]\]"
    )
    START_BOUNDARY_PATTERN = re.compile(
        r"\[\[\s*(?:بداية|جملة\s+البداية|start)\s*[:：\-]\s*"
        r"([^\]\r\n]+?)\s*\]\]"
    )
    SECTION_END_BOUNDARY_PATTERN = re.compile(
        r"\[\[\s*(?:نهاية|جملة\s+النهاية|end)\s*[:：\-]\s*"
        r"([^\]\r\n]+?)\s*\]\]"
    )
    LEGACY_HEADING_PATTERN = re.compile(
        r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?\[\[\s*([^\]\r\n]+?)\s*\]\]"
    )
    NON_MAIN_PREFIXES = (
        "بداية",
        "جملة البداية",
        "نهاية",
        "جملة النهاية",
        "السؤال",
        "سؤال",
        "جواب",
        "الإجابة",
        "إجابة",
        "تنبيه",
        "ملاحظة",
        "مثال",
        "الدليل",
        "نهاية الشرح",
        "انتهاء الشرح",
    )

    @classmethod
    def parse_items(cls, discovery_text: str) -> list[ExtractionItem]:
        logger.info(
            "[bold cyan]Parsing items from the extraction plan...[/bold cyan]"
        )
        items: list[ExtractionItem] = []
        seen_titles: set[tuple[str, str]] = set()
        main_heading_number = 0

        discovery_text = discovery_text or ""
        explicit_matches = list(
            cls.MAIN_HEADING_PATTERN.finditer(discovery_text)
        )

        if explicit_matches:
            logger.info(
                f"[bold green]Found {len(explicit_matches)} explicitly "
                "marked main headings.[/bold green]"
            )
            marked_items = []
            for index, match in enumerate(explicit_matches):
                next_start = (
                    explicit_matches[index + 1].start()
                    if index + 1 < len(explicit_matches)
                    else len(discovery_text)
                )
                section_plan = discovery_text[match.end() : next_start]
                marked_items.append(
                    (
                        match.start(),
                        match.group(1),
                        1,
                        "main",
                        cls._boundary_hint(
                            cls.START_BOUNDARY_PATTERN,
                            section_plan,
                        ),
                        cls._boundary_hint(
                            cls.SECTION_END_BOUNDARY_PATTERN,
                            section_plan,
                        ),
                    )
                )

            end_markers = list(
                cls.END_EXPLANATION_PATTERN.finditer(discovery_text)
            )
            if end_markers:
                explanation_end = end_markers[-1].end()
                end_questions = [
                    match
                    for match in cls.END_QUESTION_PATTERN.finditer(
                        discovery_text,
                        explanation_end,
                    )
                ]
                marked_items.extend(
                    (
                        match.start(),
                        match.group(1),
                        2,
                        "end_question",
                        None,
                        None,
                    )
                    for match in end_questions
                )
                if end_questions:
                    logger.info(
                        f"[bold green]Found {len(end_questions)} "
                        "end-of-lesson questions.[/bold green]"
                    )

            candidates = sorted(marked_items, key=lambda item: item[0])
        else:
            candidates = [
                (match.start(), match.group(1), 1, "main", None, None)
                for match in cls.LEGACY_HEADING_PATTERN.finditer(
                    discovery_text
                )
            ]
            logger.warning(
                "[bold yellow]No [[رئيسي: ...]] markers found; "
                "using conservative legacy heading detection.[/bold yellow]"
            )

        for _, candidate, level, kind, start_hint, end_hint in candidates:
            title = cls._clean_title(candidate)
            if kind == "main" and not cls._is_valid_main_title(
                title, explicit=bool(explicit_matches)
            ):
                continue
            if kind == "end_question" and not title:
                continue

            title_without_ordinal = (
                strip_main_heading_ordinal(title) if kind == "main" else title
            )
            normalized_title = (
                kind,
                cls._normalize_title(title_without_ordinal),
            )
            if normalized_title in seen_titles:
                continue

            if kind == "main":
                main_heading_number += 1
                title = number_main_heading(
                    title_without_ordinal,
                    main_heading_number,
                )

            items.append(
                ExtractionItem(
                    title=title,
                    level=level,
                    kind=kind,
                    start_hint=start_hint if kind == "main" else None,
                    end_hint=end_hint if kind == "main" else None,
                )
            )
            seen_titles.add(normalized_title)

        if items:
            logger.info(
                f"[bold green]Accepted {len(items)} extraction "
                "items.[/bold green]"
            )
        else:
            logger.warning(
                "[bold red]No valid extraction items found in the "
                "phase-one response.[/bold red]"
            )

        return items

    @staticmethod
    def _clean_title(title: str) -> str:
        title = title.replace("**", "").replace("__", "")
        return re.sub(r"\s+", " ", title).strip(" \t:：-–—")

    @classmethod
    def _boundary_hint(
        cls,
        pattern: re.Pattern[str],
        text: str,
    ) -> str | None:
        match = pattern.search(text)
        if not match:
            return None
        return cls._clean_title(match.group(1))

    @classmethod
    def _is_valid_main_title(cls, title: str, explicit: bool) -> bool:
        if not title or len(title) > 180:
            return False
        if explicit:
            return True

        normalized = cls._normalize_title(title)
        return not any(
            normalized.startswith(cls._normalize_title(prefix))
            for prefix in cls.NON_MAIN_PREFIXES
        )

    @staticmethod
    def _normalize_title(title: str) -> str:
        title = re.sub(r"[\u064B-\u065F\u0670]", "", title)
        title = re.sub(r"[^\u0621-\u064A0-9A-Za-z]+", " ", title)
        return re.sub(r"\s+", " ", title).strip().casefold()
