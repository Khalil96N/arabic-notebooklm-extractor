from app.browser.manager import BrowserManager
from app.config.settings import settings
from app.exporters.common import (
    normalize_implicit_lists,
    safe_output_name,
    strip_repeated_heading,
)
from app.exporters.file import FileExporter
from app.prompts.generator import PromptGenerator
from app.services.notebooklm import NotebookLMService
from app.utils.logger import logger


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
) -> str | None:
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
        prompts = PromptGenerator.generate_prompts(plan.items)

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
        sections = [
            (
                heading,
                normalize_implicit_lists(
                    strip_repeated_heading(text, heading)
                ),
            )
            for heading, text in sections
        ]

        logger.info(
            "[bold cyan]Assembling and exporting final results...[/bold cyan]"
        )
        final_text = "\n\n".join(
            f"## {heading}\n\n{text}"
            for heading, text in sections
        )
        FileExporter.save_final_transcript(final_text, output_name)
        FileExporter.save_word_document(sections, output_name)

        logger.info(
            f"[bold green]Workflow completed successfully! "
            f"Output saved as {output_name}[/bold green]"
        )
        return output_name
    except Exception as exc:
        logger.exception(
            f"[bold red]An error occurred during execution: {exc}[/bold red]"
        )
        return None
    finally:
        await browser_manager.stop()
