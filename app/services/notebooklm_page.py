from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PWTimeoutError,
)

from app.config.settings import settings
from app.services.retry_button import NotebookLMRetryButtonHandler
from app.utils.source_names import normalize_source_name, source_names_match
from app.utils.logger import logger


class NotebookLMPageClient:
    NOTEBOOKLM_URL = "https://notebooklm.google.com/"

    def __init__(self, context: BrowserContext) -> None:
        self.context = context

    async def open_configured_notebook(
        self,
        page: Page,
        notebook_name: str,
        lecture_name: str,
        book_name: str = None,
    ) -> None:
        await self.navigate(page)
        await self.wait_for_login(page)
        await self.open_notebook(page, notebook_name)
        await self.select_source(page, lecture_name, book_name)

    async def navigate(self, page: Page) -> None:
        logger.info("[bold cyan]Navigating to NotebookLM...[/bold cyan]")
        await page.goto(self.NOTEBOOKLM_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

    async def is_logged_in(self, page: Page) -> bool:
        current_url = page.url
        if "accounts.google.com" in current_url:
            return False
        if "notebooklm.google.com" not in current_url:
            return False

        checks = [
            lambda: page.get_by_text("Create notebook").is_visible(),
            lambda: page.get_by_text("Create new notebook").is_visible(),
            lambda: page.get_by_role(
                "button",
                name="Create notebook",
            ).is_visible(),
            lambda: page.locator('a[href*="/notebook/"]').first.is_visible(),
        ]
        for check in checks:
            try:
                if await check():
                    return True
            except Exception:
                continue
        return False

    async def wait_for_login(self, page: Page) -> None:
        logger.info("[bold cyan]Checking login status...[/bold cyan]")
        logger.info(f"[dim]Current URL: {page.url}[/dim]")

        if await self.is_logged_in(page):
            logger.info("[bold green]Already logged in.[/bold green]")
            return

        logger.warning(
            "[bold yellow]Login required. Please log in manually in the "
            "browser window.[/bold yellow]"
        )
        logger.warning(
            "[bold yellow]Waiting for login. Complete sign-in in the browser "
            "window; extraction will continue automatically.[/bold yellow]"
        )

        elapsed = 0
        while (
            settings.LOGIN_TIMEOUT_SECONDS <= 0
            or elapsed < settings.LOGIN_TIMEOUT_SECONDS
        ):
            await page.wait_for_timeout(3000)
            elapsed += 3
            if await self.is_logged_in(page):
                logger.info("[bold green]Login detected! Continuing...[/bold green]")
                return
            if elapsed % 30 == 0:
                logger.info(
                    f"[dim]Still waiting for login... "
                    f"({elapsed}s elapsed, URL: {page.url})[/dim]"
                )

        raise RuntimeError("Login timeout - could not detect NotebookLM dashboard.")

    async def open_notebook(self, page: Page, notebook_name: str) -> None:
        logger.info(
            f"[bold cyan]Searching for notebook '{notebook_name}'...[/bold cyan]"
        )
        await page.wait_for_timeout(3000)

        try:
            target = page.get_by_text(notebook_name, exact=False).first
            if await target.is_visible(timeout=2000):
                await self._open_notebook_title(page, target)
                logger.info(
                    f"[bold green]Opened notebook matching "
                    f"'{notebook_name}'.[/bold green]"
                )
                await page.wait_for_timeout(5000)
                return
        except Exception:
            pass

        logger.warning(
            f"[bold yellow]Could not find text '{notebook_name}'. "
            f"Trying fallback locator...[/bold yellow]"
        )
        notebooks = page.locator(
            '.project-button-title, [class*="project-button-title"]'
        )
        count = await notebooks.count()
        if count == 0:
            raise RuntimeError("Could not find any notebook links on the page.")

        logger.info(
            f"[dim]Found {count} notebook elements. Available notebooks:[/dim]"
        )
        for index in range(count):
            notebook = notebooks.nth(index)
            text = (await notebook.text_content() or "").strip()
            logger.info(f"[dim]- {text}[/dim]")
            if self._source_matches(
                notebook_name,
                text,
            ):
                await self._open_notebook_title(page, notebook)
                logger.info(
                    f"[bold green]Opened notebook: {text[:60]}[/bold green]"
                )
                await page.wait_for_timeout(5000)
                return

        first_notebook = notebooks.first
        text = (await first_notebook.text_content() or "Unknown").strip()
        await self._open_notebook_title(page, first_notebook)
        logger.warning(
            f"[bold yellow]Opened first available notebook: "
            f"{text[:60]}[/bold yellow]"
        )
        await page.wait_for_timeout(5000)

    @staticmethod
    async def _open_notebook_title(page: Page, notebook_locator) -> None:
        href = await notebook_locator.evaluate(
            """(el) => {
                const card = el.closest(
                    'mat-card, project-button, [class*="project-button"]'
                );
                const link = el.closest('a[href]')
                    || card?.querySelector('a[href*="/notebook/"]')
                    || el.querySelector?.('a[href]');
                return link?.href || "";
            }"""
        )
        if href:
            await page.goto(href, wait_until="domcontentloaded")
            return

        await notebook_locator.click(force=True)

    async def select_source(
        self,
        page: Page,
        lecture_name: str,
        book_name: str = None,
    ) -> None:
        logger.info(
            f"[bold cyan]Looking for source '{lecture_name}' "
            f"(and optionally book '{book_name}') in sidebar...[/bold cyan]"
        )
        await page.wait_for_timeout(3000)
        checkboxes = page.locator('input[type="checkbox"]')

        try:
            await checkboxes.first.wait_for(state="attached", timeout=15000)
        except Exception:
            logger.warning(
                "[bold yellow]Timeout waiting for checkboxes. They might "
                "be missing or still loading.[/bold yellow]"
            )

        checkbox_count = await checkboxes.count()
        logger.info(f"[dim]Found {checkbox_count} source checkboxes.[/dim]")

        for index in range(checkbox_count):
            checkbox = checkboxes.nth(index)
            try:
                if await checkbox.is_checked():
                    await checkbox.click(force=True)
                    await page.wait_for_timeout(300)
            except Exception:
                continue

        await page.wait_for_timeout(1000)
        lecture_found = False
        book_found = book_name is None

        for index in range(checkbox_count):
            checkbox = checkboxes.nth(index)
            try:
                text = await checkbox.evaluate(
                    "(el) => { "
                    "let p = el.parentElement; "
                    "while (p && p.innerText.length < 5) p = p.parentElement; "
                    'return p ? p.innerText : ""; '
                    "}"
                )
                normalized_text = normalize_source_name(text)
                logger.info(
                    f"[dim]Evaluating source {index}: "
                    f"'{text}' -> '{normalized_text}'[/dim]"
                )

                if (
                    not lecture_found
                    and self._source_matches(
                        lecture_name,
                        text,
                    )
                    and len(text) < 300
                ):
                    await checkbox.click(force=True)
                    lecture_found = True
                    logger.info(
                        f"[bold green]Successfully checked lecture source: "
                        f"{text.strip()[:60]}[/bold green]"
                    )

                if (
                    book_name
                    and not book_found
                    and self._source_matches(
                        book_name,
                        text,
                    )
                    and len(text) < 300
                ):
                    await checkbox.click(force=True)
                    book_found = True
                    logger.info(
                        f"[bold green]Successfully checked book source: "
                        f"{text.strip()[:60]}[/bold green]"
                    )
            except Exception:
                continue

        if not lecture_found:
            logger.error(
                f"[bold red]Could not find lecture source "
                f"'{lecture_name}'![/bold red]"
            )
            raise RuntimeError(f"Source '{lecture_name}' not found.")

        if book_name and not book_found:
            logger.warning(
                f"[bold yellow]Could not find book source '{book_name}'! "
                f"Proceeding with lecture only.[/bold yellow]"
            )

        await page.wait_for_timeout(2000)

    async def send_prompt(self, page: Page, prompt: str) -> None:
        logger.info("[bold cyan]Locating chat input...[/bold cyan]")
        chat_input = page.get_by_placeholder(
            "Type something",
            exact=False,
        ).first

        try:
            await chat_input.wait_for(state="visible", timeout=15000)
        except PWTimeoutError:
            logger.warning(
                "[bold yellow]Primary placeholder not found, trying "
                "fallback...[/bold yellow]"
            )
            chat_input = page.locator(
                'textarea, [contenteditable="true"], input[type="text"]'
            ).last
            await chat_input.wait_for(state="visible", timeout=10000)

        logger.info("[bold cyan]Typing extraction prompt...[/bold cyan]")
        await chat_input.click()
        await chat_input.fill(prompt)
        await page.wait_for_timeout(500)

        prompt_sent = False
        for selector in (
            'button[aria-label="Send"]',
            'button[aria-label*="send" i]',
            'button[type="submit"]',
        ):
            try:
                send_button = page.locator(selector).last
                if await send_button.is_visible():
                    await send_button.click()
                    prompt_sent = True
                    logger.info(
                        "[bold green]Prompt sent via send button.[/bold green]"
                    )
                    break
            except Exception:
                continue

        if not prompt_sent:
            await chat_input.press("Enter")
            logger.info("[bold green]Prompt sent via Enter key.[/bold green]")

        await page.wait_for_timeout(500)

    async def wait_for_response(
        self,
        page: Page,
        marker: str = None,
    ) -> str:
        logger.info(
            f"[bold cyan]Waiting for response generation "
            f"(timeout: {settings.TIMEOUT_MS // 1000}s)...[/bold cyan]"
        )
        retry_handler = NotebookLMRetryButtonHandler(page)
        await retry_handler.ignore_existing_buttons()
        await page.wait_for_timeout(8000)
        previous_text = ""
        stable_count = 0
        elapsed = 0
        poll_interval = 3000

        while elapsed < settings.TIMEOUT_MS:
            if await retry_handler.click_if_present():
                previous_text = ""
                stable_count = 0
                elapsed = 0
                continue

            current_text = (
                await self.response_by_marker(page, marker)
                if marker
                else await self.latest_response(page)
            )
            if current_text and len(current_text) > 5:
                if current_text == previous_text:
                    stable_count += 1
                    if stable_count >= 4:
                        logger.info(
                            "[bold green]Response generation complete."
                            "[/bold green]"
                        )
                        return current_text
                else:
                    stable_count = 0
                    logger.info(
                        f"[dim]Generating... ({len(current_text)} chars so far)"
                        f"[/dim]"
                    )

            previous_text = current_text
            await page.wait_for_timeout(poll_interval)
            elapsed += poll_interval

        if previous_text and len(previous_text) > 5:
            logger.warning(
                "[bold yellow]Timed out but returning partial response."
                "[/bold yellow]"
            )
            return previous_text

        raise RuntimeError(
            "Failed to extract response from NotebookLM within the timeout."
        )

    async def latest_response(self, page: Page) -> str:
        for selector in self.response_selectors():
            try:
                elements = await page.locator(selector).all()
                if elements:
                    text = await elements[-1].inner_text()
                    if text and len(text.strip()) > 10:
                        return text.strip()
            except Exception:
                continue

        try:
            main_area = page.locator(
                'main, [role="main"], .chat-container'
            ).first
            if await main_area.is_visible():
                return (await main_area.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def response_by_marker(self, page: Page, marker: str) -> str:
        candidates = await self.response_candidates(page)
        matching = [
            text
            for text in candidates
            if 0 <= text.casefold().find(marker.casefold()) <= 500
        ]
        return min(matching, key=len) if matching else ""

    async def response_candidates(self, page: Page) -> list[str]:
        candidates = []
        seen = set()
        for selector in self.response_selectors():
            try:
                elements = await page.locator(selector).all()
                for element in elements:
                    text = await element.inner_text()
                    if text and len(text.strip()) > 10:
                        text = text.strip()
                        if text not in seen:
                            candidates.append(text)
                            seen.add(text)
            except Exception:
                continue
        return candidates

    @staticmethod
    def response_selectors() -> tuple[str, ...]:
        return (
            'div[data-message-author-role="assistant"]',
            ".response-container",
            ".message-content",
            'div[role="log"] > div:last-child',
            ".chat-message:last-child",
            "div.markdown",
        )

    @staticmethod
    def _source_matches(target: str, candidate: str) -> bool:
        return source_names_match(target, candidate)
