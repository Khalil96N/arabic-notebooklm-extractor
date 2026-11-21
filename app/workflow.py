import re

from app.browser.manager import BrowserManager
from app.config.settings import settings
from app.exporters.common import (
    compact_russian_classroom_content,
    merge_adjacent_rule_chunks,
    merge_repeated_letter_entries,
    normalize_arabic_key,
    normalize_implicit_lists,
    safe_output_name,
    strip_repeated_heading,
)
from app.exporters.file import FileExporter
from app.exporters.text import TextExporter
from app.exporters.russian_course import (
    get_prior_rule_names,
    update_cumulative_outputs,
)
from app.models.schemas import PromptItem
from app.prompts.generator import PromptGenerator
from app.prompts.profiles import (
    DEFAULT_CONTENT_TYPE,
    ContentType,
    validate_content_type,
)
from app.prompts.russian_course_templates import split_chunk_response
from app.services.notebooklm import NotebookLMService
from app.utils.logger import logger


_EMPTY_BUCKET_MESSAGES = frozenset(
    normalize_arabic_key(message)
    for message in (
        "لا يوجد حرف جديد في هذا الجزء.",
        "لا توجد قاعدة جديدة في هذا الجزء.",
        "لا يوجد حوار تعليمي في هذا الجزء.",
    )
)
_ENGLISH_LOGISTICS_BLOCK = re.compile(
    r"<logistics>\s*(.*?)\s*</logistics>",
    flags=re.IGNORECASE | re.DOTALL,
)


def aggregate_russian_chunks(
    prompts: list[PromptItem],
    sections: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], str]:
    """Merge the per-chunk combined calls back into one section per bucket.

    Each Russian lesson chunk produces one combined letters/rules/dialogues/
    vocabulary call (plus one recap call for the last chunk), so this splits
    that combined response into its four buckets, cleans each part the same
    way the old per-bucket calls were cleaned (heading/classroom-repetition
    stripping for the summary buckets, none of that for vocabulary), and
    joins same-bucket text across chunks in chunk order.
    """
    summary_by_heading: dict[str, list[str]] = {}
    vocabulary_parts: list[str] = []

    def add_summary(heading: str, raw_text: str) -> None:
        text = strip_repeated_heading(raw_text, heading)
        text = compact_russian_classroom_content(text)
        text = normalize_implicit_lists(text)
        if not text.strip():
            return
        # A chunk that legitimately found nothing new returns only that
        # fallback sentence; keeping every one of those in the final
        # document would litter it with "no new letter/rule/dialogue in
        # this part" lines for every empty chunk.
        if normalize_arabic_key(text) in _EMPTY_BUCKET_MESSAGES:
            return
        if heading not in summary_by_heading:
            summary_by_heading[heading] = []
        summary_by_heading[heading].append(text)

    def add_vocabulary(raw_text: str) -> None:
        text = normalize_implicit_lists(raw_text)
        if text.strip():
            vocabulary_parts.append(text)

    for prompt, (heading, text) in zip(prompts, sections):
        if prompt.output_kind == "combined":
            parts = split_chunk_response(text)
            add_summary("الحروف الجديدة", parts["letters"])
            add_summary("القواعد والتطبيقات", parts["rules"])
            add_summary("الحوارات الروسية", parts["dialogues"])
            add_vocabulary(parts["vocabulary"])
        elif prompt.output_kind == "summary":
            add_summary(heading, text)
        elif prompt.output_kind == "vocabulary":
            add_vocabulary(text)

    def join_bucket(heading: str) -> str:
        chunk_texts = summary_by_heading[heading]
        if heading == "القواعد والتطبيقات":
            # A rule the teacher starts near one chunk boundary and finishes
            # in the next comes back as two separate chunk calls; merge a
            # matching pair of <subheading> blocks instead of leaving both.
            return merge_adjacent_rule_chunks(chunk_texts)
        if heading == "الحروف الجديدة":
            # The same letter is re-taught across chunks; keep it once.
            return merge_repeated_letter_entries(chunk_texts)
        return "\n\n".join(chunk_texts)

    summary_sections = [
        (heading, join_bucket(heading))
        for heading in (
            "الحروف الجديدة",
            "القواعد والتطبيقات",
            "الحوارات الروسية",
            "الخلاصة والواجب",
        )
        if heading in summary_by_heading
    ]
    vocabulary_text = "\n\n".join(vocabulary_parts)
    return summary_sections, vocabulary_text


def aggregate_english_sections(
    prompts: list[PromptItem],
    sections: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Move useful course logistics into one final section and drop its scan."""
    if len(prompts) != len(sections):
        raise ValueError("English prompts and extraction results must align.")

    cleaned_sections: list[tuple[str, str]] = []
    logistics: list[str] = []
    seen_logistics: set[str] = set()
    empty_logistics = {
        normalize_arabic_key(message)
        for message in (
            "لا توجد معلومات تنظيمية مهمة.",
            "لا توجد معلومات تنظيمية مهمة",
            "لا توجد معلومات تنظيمية",
            "لا توجد معلومات إدارية مهمة.",
            "لا توجد معلومات ادارية مهمة.",
            "لا توجد معلومات عملية مهمة.",
            "لا يوجد شيء مهم.",
            "لم ترد معلومات تنظيمية مهمة.",
            "لا يوجد",
            "none",
            "n/a",
            "no relevant logistics",
            "no important logistics",
        )
    }

    for prompt, (heading, raw_text) in zip(prompts, sections):
        def collect_logistics(match: re.Match[str]) -> str:
            for line in match.group(1).splitlines():
                item = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
                item = re.sub(r"\s+", " ", item).strip()
                if not item:
                    continue
                key = normalize_arabic_key(item)
                if key in empty_logistics or key in seen_logistics:
                    continue
                seen_logistics.add(key)
                logistics.append(item)
            return ""

        # NotebookLM may emit LaTeX commands despite the UnicodeMath prompt.
        # Canonicalize only English notes before both final exports.
        text = re.sub(
            r"\\(sum|times|cdot|leq|geq|neq)(?![A-Za-z])",
            lambda match: {
                "sum": "∑", "times": "×", "cdot": "×",
                "leq": "≤", "geq": "≥", "neq": "≠",
            }[match.group(1)],
            raw_text,
        )
        text = re.sub(
            r"∑_\{([^}]+)\}\^\{?([A-Za-z0-9]+)\}?",
            lambda match: f"∑_({match.group(1)})^{match.group(2)}",
            text,
        )
        text = _ENGLISH_LOGISTICS_BLOCK.sub(collect_logistics, text)
        # Do not leak a malformed or unclosed internal marker into the files.
        text = re.sub(r"</?logistics>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()
        if prompt.output_kind != "logistics":
            cleaned_sections.append((heading, text))

    if logistics:
        cleaned_sections.append(
            (
                "معلومات تنظيمية مهمة",
                "\n".join(f"- {item}" for item in logistics),
            )
        )
    return cleaned_sections


def next_output_name(lecture_name: str) -> str:
    safe_name = safe_output_name(lecture_name)

    if not (
        (settings.OUTPUT_DIR / f"{safe_name}.md").exists()
        or (settings.OUTPUT_DIR / f"{safe_name}.docx").exists()
    ):
        return safe_name

    version = 2
    while True:
        versioned_name = f"{safe_name}_v{version}"
        if not (
            (settings.OUTPUT_DIR / f"{versioned_name}.md").exists()
            or (settings.OUTPUT_DIR / f"{versioned_name}.docx").exists()
        ):
            return versioned_name
        version += 1


async def run_workflow(
    profile_name: str,
    notebook_name: str,
    lecture_name: str,
    book_name: str = None,
    content_type: ContentType = DEFAULT_CONTENT_TYPE,
) -> str | None:
    content_type = validate_content_type(content_type)
    browser_manager = BrowserManager()
    try:
        context = await browser_manager.start(profile_name)
        service = NotebookLMService(context)
        logger.info(
            f"[bold magenta]Starting extraction workflow for: "
            f"'{lecture_name}' in notebook '{notebook_name}'[/bold magenta]"
        )

        plan = await service.discover_extraction_plan(
            notebook_name,
            lecture_name,
            book_name,
            content_type,
        )
        if not plan.discovery_text:
            logger.error(
                "[bold red]Failed to discover an extraction plan. "
                "The response is empty."
                "[/bold red]"
            )
            return None

        if not plan.items:
            FileExporter.save_discovery_response(plan.discovery_text)
            FileExporter.save_extraction_items(plan.items)
            logger.error(
                "[bold red]No valid extraction items were detected. "
                "Saved the discovery response and stopped before section "
                "extraction.[/bold red]"
            )
            return None

        logger.info(
            "[bold cyan]Generating section extraction prompts...[/bold cyan]"
        )
        prompts = PromptGenerator.generate_prompts(
            plan.items,
            content_type,
            prior_rule_names=(
                get_prior_rule_names(lecture_name)
                if content_type == "russian"
                else None
            ),
        )

        logger.info(
            "[bold cyan]Saving Phase 1 extraction plan...[/bold cyan]"
        )
        FileExporter.save_discovery_response(plan.discovery_text)
        FileExporter.save_extraction_items(plan.items)
        FileExporter.save_prompts(prompts)

        logger.info(
            "[bold magenta]Starting Phase 2: Parallel Extraction..."
            "[/bold magenta]"
        )
        output_name = next_output_name(lecture_name)
        sections = await service.extract_sections(prompts, output_name)

        logger.info(
            "[bold cyan]Assembling and exporting final results...[/bold cyan]"
        )
        if content_type == "russian":
            # Cleaning happens per-bucket inside aggregate_russian_chunks,
            # after it splits each chunk's combined response apart, so the
            # raw sections are passed through untouched here.
            summary_sections, vocabulary_text = aggregate_russian_chunks(
                prompts, sections
            )
            summary_path, vocabulary_path, lecture_number = (
                update_cumulative_outputs(
                    lecture_name,
                    summary_sections,
                    vocabulary_text,
                )
            )
            logger.info(
                f"[bold green]Updated cumulative Russian lecture "
                f"{lecture_number}: {summary_path.name} and "
                f"{vocabulary_path.name}[/bold green]"
            )
        else:
            if content_type == "english":
                sections = aggregate_english_sections(prompts, sections)
            cleaned_sections = [
                (
                    heading,
                    normalize_implicit_lists(
                        strip_repeated_heading(text, heading)
                    ),
                )
                for heading, text in sections
            ]
            sections = cleaned_sections
            final_text = "\n\n".join(
                f"## {heading}\n\n{text}"
                for heading, text in sections
            )
            FileExporter.save_final_transcript(final_text, output_name)
            FileExporter.save_word_document(
                sections,
                output_name,
                number_main_headings=content_type != "english",
                document_title=(
                    lecture_name if content_type == "english" else None
                ),
            )

        logger.info(
            f"[bold green]Workflow completed successfully! "
            f"Output saved as {output_name}[/bold green]"
        )
        TextExporter.cleanup_diagnostics()
        return output_name
    except Exception as exc:
        logger.exception(
            f"[bold red]An error occurred during execution: {exc}[/bold red]"
        )
        return None
    finally:
        await browser_manager.stop()
