import asyncio
import re
import uuid

from playwright.async_api import BrowserContext, Page

from app.config.settings import settings
from app.exporters.file import FileExporter
from app.models.schemas import PromptItem
from app.services.notebooklm_page import NotebookLMPageClient
from app.utils.logger import logger


class SectionExtractor:
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 3
    FAILED_RESPONSE_PHRASES = (
        "unable to answer",
        "can't answer",
        "i'm having trouble responding right now",
        "i’m having trouble responding right now",
        "i am having trouble responding right now",
        "defining invalid interpretations...",
    )

    def __init__(
        self,
        context: BrowserContext,
        page_client: NotebookLMPageClient,
        current_page: Page,
        notebook_url: str,
        lecture_name: str,
        book_name: str = None,
    ) -> None:
        self.context = context
        self.page_client = page_client
        self.current_page = current_page
        self.notebook_url = notebook_url
        self.lecture_name = lecture_name
        self.book_name = book_name

    async def extract(
        self,
        prompts: list[PromptItem],
        output_name: str,
    ) -> list[tuple[str, str]]:
        if not prompts:
            await self.current_page.close()
            return []

        worker_count = min(
            max(1, settings.PARALLEL_EXTRACTIONS),
            len(prompts),
        )
        logger.info(
            f"[bold magenta]Starting parallel extraction with "
            f"{worker_count} tab(s) in the same Chrome window.[/bold magenta]"
        )

        worker_pages = await self.prepare_worker_tabs(worker_count)
        queue: asyncio.Queue[tuple[int, PromptItem]] = asyncio.Queue()
        for index, prompt_item in enumerate(prompts):
            queue.put_nowait((index, prompt_item))

        results: list[str | None] = [None] * len(prompts)
        failed_indexes: set[int] = set()
        save_lock = asyncio.Lock()

        async def save_completed_sections() -> None:
            # The cumulative Russian-course flow writes its two final Word
            # files only after every combined/vocabulary request finishes.
            if any(
                prompt.output_kind in ("vocabulary", "combined")
                for prompt in prompts
            ):
                return
            completed_sections = [
                (prompts[index].heading, text)
                for index, text in enumerate(results)
                if text is not None
                and prompts[index].output_kind == "summary"
            ]
            if not completed_sections:
                return
            try:
                FileExporter.save_word_document(
                    completed_sections,
                    output_name,
                )
            except Exception as exc:
                logger.error(
                    f"[bold red]Failed to incrementally save Word document: "
                    f"{exc}[/bold red]"
                )

        async def worker(worker_number: int, page: Page) -> None:
            while True:
                try:
                    index, prompt_item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                logger.info(
                    f"[bold cyan]Tab {worker_number}: processing "
                    f"{index + 1}/{len(prompts)} "
                    f"'{prompt_item.heading}'...[/bold cyan]"
                )
                marker = f"NBX-{index + 1}-{uuid.uuid4().hex[:8]}"
                try:
                    section_text = await self.extract_with_retries(
                        page,
                        prompt_item,
                        marker,
                    )

                    if section_text is None:
                        failed_indexes.add(index)
                    else:
                        results[index] = section_text
                        async with save_lock:
                            await save_completed_sections()
                finally:
                    queue.task_done()

        try:
            workers = [
                asyncio.create_task(worker(index + 1, page))
                for index, page in enumerate(worker_pages)
            ]
            await asyncio.gather(*workers)

            if failed_indexes:
                logger.warning(
                    f"[bold yellow]{len(failed_indexes)} request(s) failed "
                    f"in parallel and will be retried sequentially."
                    f"[/bold yellow]"
                )
                fallback_page = worker_pages[0]
                for index in sorted(failed_indexes):
                    results[index] = (
                        await self.extract_with_retries(
                            fallback_page,
                            prompts[index],
                            marker=None,
                        )
                        or ""
                    )
                    async with save_lock:
                        await save_completed_sections()
        finally:
            for page in worker_pages:
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception:
                    pass

        return [
            (prompt.heading, results[index] or "")
            for index, prompt in enumerate(prompts)
        ]

    async def prepare_worker_tabs(self, worker_count: int) -> list[Page]:
        pages = [self.current_page]
        for tab_number in range(2, worker_count + 1):
            logger.info(
                f"[bold cyan]Preparing worker tab "
                f"{tab_number}/{worker_count} in the same window..."
                f"[/bold cyan]"
            )
            page = await self.context.new_page()
            await page.goto(self.notebook_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            await self.page_client.select_source(
                page,
                self.lecture_name,
                self.book_name,
            )
            pages.append(page)
        return pages

    async def extract_with_retries(
        self,
        page: Page,
        prompt_item: PromptItem,
        marker: str | None = None,
    ) -> str | None:
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                current_marker = marker
                if marker and attempt > 1:
                    current_marker = f"NBX-RETRY-{uuid.uuid4().hex[:10]}"

                prompt_text = prompt_item.prompt_text
                if current_marker:
                    prompt_text += (
                        f"\n\nابدأ بسطر: {prompt_item.heading} "
                        f"[[{current_marker}]]"
                    )

                previous_response = await self.page_client.latest_response(page)
                await self.page_client.send_prompt(page, prompt_text)
                section_text = await self.page_client.wait_for_response(
                    page,
                    marker=current_marker,
                    previous_response=previous_response,
                )
                section_text = self.remove_task_marker(
                    section_text,
                    current_marker,
                )
                if not self.is_failed_response(section_text):
                    return section_text

                logger.warning(
                    f"[bold yellow]NotebookLM returned an invalid response "
                    f"for '{prompt_item.heading}'. "
                    f"Retry {attempt}/{self.MAX_RETRIES}...[/bold yellow]"
                )
            except Exception as exc:
                logger.warning(
                    f"[bold yellow]Request failed for "
                    f"'{prompt_item.heading}' "
                    f"({attempt}/{self.MAX_RETRIES}): "
                    f"{exc}[/bold yellow]"
                )

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY_SECONDS)

        logger.error(
            f"[bold red]Failed to get a valid response for "
            f"'{prompt_item.heading}' after "
            f"{self.MAX_RETRIES} retries.[/bold red]"
        )
        return None

    @staticmethod
    def is_failed_response(section_text: str) -> bool:
        if not section_text or len(section_text.strip()) <= 5:
            return True
        lower_text = section_text.lower()
        return any(
            phrase in lower_text
            for phrase in SectionExtractor.FAILED_RESPONSE_PHRASES
        )

    @staticmethod
    def remove_task_marker(text: str, marker: str | None = None) -> str:
        if not marker:
            return text.strip()
        marker_pattern = re.escape(marker)
        return re.sub(
            rf"(?:\[\[\s*)?{marker_pattern}(?:\s*\]\])?\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
