import re

from app.config.settings import settings
from app.exporters.common import (
    clean_spacing,
    ensure_output_dir,
    safe_output_name,
)
from app.models.schemas import ExtractionItem, PromptItem
from app.utils.logger import logger


class TextExporter:
    @staticmethod
    def save_discovery_response(text: str) -> None:
        """Save the phase-one response under its legacy diagnostic filename."""
        ensure_output_dir()
        path = settings.OUTPUT_DIR / "transcript.txt"
        path.write_text(text, encoding="utf-8")
        logger.info(
            f"[bold green]Saved extraction-plan response to {path}[/bold green]"
        )

    @staticmethod
    def save_extraction_items(items: list[ExtractionItem]) -> None:
        """Save parsed phase-one items under the legacy diagnostic filename."""
        ensure_output_dir()
        path = settings.OUTPUT_DIR / "headings.txt"
        lines = [f"{'#' * item.level} {item.title}" for item in items]
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            f"[bold green]Saved extraction items to {path}[/bold green]"
        )

    @staticmethod
    def save_prompts(prompts: list[PromptItem]) -> None:
        ensure_output_dir()
        path = settings.OUTPUT_DIR / "section_prompts.md"
        prompt_blocks = [
            (
                f"## {prompt.heading}\n\n"
                f"```text\n{prompt.prompt_text}\n```\n\n---\n\n"
            )
            for prompt in prompts
        ]
        path.write_text(
            "# Section Prompts\n\n" + "".join(prompt_blocks),
            encoding="utf-8",
        )
        logger.info(f"[bold green]Saved section prompts to {path}[/bold green]")

    @staticmethod
    def save_final_transcript(
        text: str,
        lecture_name: str = "final_transcript",
    ) -> None:
        ensure_output_dir()
        text = clean_spacing(text)
        text = re.sub(r"([^\n])\s*(##\s+)", r"\1\n\n\2", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        path = settings.OUTPUT_DIR / f"{safe_output_name(lecture_name)}.md"
        path.write_text(text, encoding="utf-8")
        logger.info(
            f"[bold green]Saved final assembled transcript to "
            f"{path}[/bold green]"
        )
