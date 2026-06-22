from app.exporters.common import (
    clean_spacing,
    ensure_output_dir,
    get_current_dates,
)
from app.exporters.text import TextExporter
from app.exporters.word import WordExporter
from app.models.schemas import ExtractionItem, PromptItem
from app.utils.arabic import arabic_ordinal


class FileExporter:
    """Backward-compatible facade for all output formats."""

    ensure_output_dir = staticmethod(ensure_output_dir)
    clean_spacing = staticmethod(clean_spacing)
    arabic_ordinal = staticmethod(arabic_ordinal)
    get_current_dates = staticmethod(get_current_dates)

    @staticmethod
    def save_discovery_response(text: str) -> None:
        TextExporter.save_discovery_response(text)

    @staticmethod
    def save_extraction_items(items: list[ExtractionItem]) -> None:
        TextExporter.save_extraction_items(items)

    @staticmethod
    def save_prompts(prompts: list[PromptItem]) -> None:
        TextExporter.save_prompts(prompts)

    @staticmethod
    def save_final_transcript(
        text: str,
        lecture_name: str = "final_transcript",
    ) -> None:
        TextExporter.save_final_transcript(text, lecture_name)

    @classmethod
    def save_word_document(
        cls,
        sections: list,
        lecture_name: str = "final_transcript",
    ) -> None:
        WordExporter.save(
            sections=sections,
            lecture_name=lecture_name,
            clean_text=cls.clean_spacing,
            date_provider=cls.get_current_dates,
        )
