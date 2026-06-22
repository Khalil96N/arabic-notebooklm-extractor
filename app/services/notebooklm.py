from playwright.async_api import BrowserContext, Page

from app.models.schemas import ExtractionPlan, PromptItem
from app.parser.extraction_plan import ExtractionPlanParser
from app.prompts.templates import build_outline_prompt
from app.services.notebooklm_page import NotebookLMPageClient
from app.services.section_extractor import SectionExtractor
from app.utils.logger import logger


class NotebookLMService:
    """Discovers the extraction plan, then extracts every item separately."""

    def __init__(self, context: BrowserContext) -> None:
        self.context = context
        self.page_client = NotebookLMPageClient(context)
        self.current_page: Page | None = None
        self.notebook_url: str | None = None
        self.lecture_name: str | None = None
        self.book_name: str | None = None

    async def discover_extraction_plan(
        self,
        notebook_name: str,
        lecture_name: str,
        book_name: str | None = None,
    ) -> ExtractionPlan:
        self.lecture_name = lecture_name
        self.book_name = book_name
        self.current_page = await self.context.new_page()

        await self.page_client.open_configured_notebook(
            self.current_page,
            notebook_name,
            lecture_name,
            book_name,
        )
        self.notebook_url = self.current_page.url
        await self.page_client.send_prompt(
            self.current_page,
            build_outline_prompt(lecture_name, book_name),
        )
        discovery_text = await self.page_client.wait_for_response(
            self.current_page
        )

        logger.info(
            f"[bold green]Received an extraction plan of "
            f"{len(discovery_text)} characters.[/bold green]"
        )
        return ExtractionPlan(
            discovery_text=discovery_text,
            items=ExtractionPlanParser.parse_items(discovery_text),
        )

    async def extract_sections(
        self,
        prompts: list[PromptItem],
        output_name: str,
    ) -> list[tuple[str, str]]:
        if not self.current_page or not self.notebook_url:
            raise RuntimeError(
                "No extraction plan is active. "
                "Run discover_extraction_plan first."
            )
        if not self.lecture_name:
            raise RuntimeError("The active lecture name is missing.")

        extractor = SectionExtractor(
            context=self.context,
            page_client=self.page_client,
            current_page=self.current_page,
            notebook_url=self.notebook_url,
            lecture_name=self.lecture_name,
            book_name=self.book_name,
        )
        return await extractor.extract(prompts, output_name)
