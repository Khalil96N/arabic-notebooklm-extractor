import re
from time import monotonic

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PWTimeoutError,
)
from urllib.parse import urlparse

from app.config.settings import settings
from app.services.retry_button import NotebookLMRetryButtonHandler
from app.utils.source_names import normalize_source_name, source_names_match
from app.utils.logger import logger


class NotebookLMPageClient:
    NOTEBOOKLM_URL = "https://notebook.google.com/"
    NOTEBOOKLM_HOSTS = ("notebook.google.com", "notebooklm.google.com")

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
        if not any(host in current_url for host in self.NOTEBOOKLM_HOSTS):
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

        # NotebookLM's current dashboard uses notebook.google.com and its
        # localized/experiment variants do not always expose the legacy
        # "Create notebook" labels or /notebook/ links immediately. Reaching
        # either NotebookLM host without an accounts.google.com redirect means
        # Google authentication has completed; notebook discovery performs the
        # stricter page-content check next.
        return True

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
        target_url = urlparse(notebook_name)
        if target_url.scheme or target_url.netloc:
            if (
                target_url.scheme != "https"
                or target_url.hostname not in self.NOTEBOOKLM_HOSTS
                or not target_url.path.startswith("/notebook/")
            ):
                raise ValueError(
                    "Notebook URL must point to a NotebookLM notebook."
                )
            logger.info(
                "[bold cyan]Opening the specified NotebookLM URL...[/bold cyan]"
            )
            await page.goto(notebook_name, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            logger.info("[bold green]Opened the specified notebook.[/bold green]")
            return

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
        select_all_matches = lecture_name.casefold().startswith("all:")
        lecture_target = (
            lecture_name.split(":", 1)[1].strip()
            if select_all_matches
            else lecture_name
        )
        if select_all_matches and not lecture_target:
            raise ValueError("ALL: source selector requires a match target.")
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

        lecture_found = False
        lecture_match_count = 0
        book_found = book_name is None
        source_rows: list[tuple[int, str]] = []
        desired_indices: set[int] = set()
        select_all_index: int | None = None

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

                # Keep the global control out of the real source set, but
                # retain it for the default all-selected fast path.
                if normalized_text == "selectall":
                    select_all_index = index
                    continue

                source_rows.append((index, text))

                if (
                    (select_all_matches or not lecture_found)
                    and self._source_matches(
                        lecture_target,
                        text,
                    )
                    and len(text) < 300
                ):
                    desired_indices.add(index)
                    lecture_found = True
                    lecture_match_count += 1

                if (
                    book_name
                    and not book_found
                    and self._source_matches(
                        book_name,
                        text,
                    )
                    and len(text) < 300
                ):
                    desired_indices.add(index)
                    book_found = True
            except Exception:
                continue

        if not lecture_found:
            logger.error(
                f"[bold red]Could not find lecture source "
                f"'{lecture_name}'![/bold red]"
            )
            raise RuntimeError(f"Source '{lecture_name}' not found.")

        if select_all_matches:
            logger.info(
                f"[bold green]Successfully checked {lecture_match_count} "
                f"lecture sources matching '{lecture_target}'.[/bold green]"
            )

        if book_name and not book_found:
            logger.warning(
                f"[bold yellow]Could not find book source '{book_name}'! "
                f"Proceeding with lecture only.[/bold yellow]"
            )

        async def enforce_checkbox_state(index: int, desired_state: bool) -> None:
            checkbox = checkboxes.nth(index)
            if await checkbox.is_checked() == desired_state:
                return

            # Activate the component's real label. Clicking the outer
            # mat-checkbox host alone does not toggle its native input in
            # the current NotebookLM UI, including Select all sources.
            await checkbox.evaluate(
                "(element) => { const host = element.closest('mat-checkbox'); "
                "(host?.querySelector('label') || element).click(); }"
            )
            await page.wait_for_timeout(500)

            if await checkbox.is_checked() != desired_state:
                raise RuntimeError(
                    "Could not enforce the requested NotebookLM source "
                    "selection."
                )

        # A newly opened notebook normally has every source selected. Clear
        # that in one click, then select only the requested recording/book.
        # Mixed or already narrow selections retain the per-row fallback.
        if select_all_index is not None:
            global_checkbox = checkboxes.nth(select_all_index)
            if await global_checkbox.is_checked():
                try:
                    await enforce_checkbox_state(select_all_index, False)
                except Exception:
                    logger.warning("Select-all fast clear failed; checking each source instead.")
        for index in sorted(desired_indices):
            await enforce_checkbox_state(index, True)
        for index, _text in source_rows:
            if index not in desired_indices:
                await enforce_checkbox_state(index, False)

        selected_sources: list[str] = []
        for index, text in source_rows:
            if await checkboxes.nth(index).is_checked():
                selected_sources.append(text.strip())

        expected_selected_count = len(desired_indices)
        if len(selected_sources) != expected_selected_count:
            raise RuntimeError(
                "NotebookLM source selection verification failed: "
                f"expected {expected_selected_count}, found "
                f"{len(selected_sources)}."
            )

        logger.info(
            "[bold green]Verified final selected sources "
            f"({len(selected_sources)}): "
            f"{', '.join(selected_sources)}[/bold green]"
        )

        await page.wait_for_timeout(2000)

    async def send_prompt(
        self, page: Page, prompt: str, *, verify_sent: bool = False
    ) -> None:
        logger.info("[bold cyan]Locating chat input...[/bold cyan]")
        chat_input = page.get_by_placeholder(
            "Type something",
            exact=False,
        ).first

        try:
            if not await chat_input.count():
                raise PWTimeoutError("Primary placeholder is absent.")
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
        await page.wait_for_timeout(1000)

        prompt_sent = False
        send_selectors = (
            'button[aria-label="Send"]',
            'button[aria-label*="send" i]',
            'button[aria-label*="إرسال" i]',
            'button[type="submit"]',
            'button:has(mat-icon:has-text("send"))',
            'button:has(mat-icon:has-text("arrow_upward"))',
            'button:has-text("send")',
            'button:has-text("arrow_upward")',
        )
        for _ in range(16):
            for selector in send_selectors:
                try:
                    send_button = page.locator(selector).last
                    if (
                        await send_button.is_visible(timeout=300)
                        and await send_button.is_enabled(timeout=300)
                    ):
                        await send_button.click()
                        prompt_sent = True
                        logger.info(
                            "[bold green]Prompt sent via send button."
                            "[/bold green]"
                        )
                        break
                except Exception:
                    continue
            if prompt_sent:
                break
            await page.wait_for_timeout(500)

        if not prompt_sent:
            try:
                await chat_input.press("Control+Enter")
                await page.wait_for_timeout(500)
            except Exception:
                pass
            await chat_input.press("Enter")
            logger.warning(
                "[bold yellow]Prompt sent via keyboard fallback."
                "[/bold yellow]"
            )

        await page.wait_for_timeout(500)

        if verify_sent:
            try:
                await page.wait_for_function(
                    "element => !element.value && !element.textContent?.trim()",
                    arg=await chat_input.element_handle(),
                    timeout=8000,
                )
            except PWTimeoutError as exc:
                raise RuntimeError(
                    "NotebookLM did not submit the prompt; the chat input "
                    f"still contains {len(prompt)} characters."
                ) from exc

    async def wait_for_response(
        self,
        page: Page,
        marker: str = None,
        previous_response: str | None = None,
        *,
        strict_marker: bool = False,
        expected_heading: str | None = None,
    ) -> str:
        if strict_marker and not marker:
            raise ValueError("Strict response matching requires a task marker.")
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
        started_at = monotonic()
        poll_interval = 3000
        marker_fallback_logged = False

        while elapsed < settings.TIMEOUT_MS:
            if await retry_handler.click_if_present():
                previous_text = ""
                stable_count = 0
                elapsed = 0
                started_at = monotonic()
                continue

            if marker:
                current_text = await self.response_by_marker(
                    page, marker,
                    **({"marker_at_start": True} if strict_marker else {}),
                    **({"expected_heading": expected_heading} if strict_marker and expected_heading else {}),
                )
                if (
                    not current_text
                    and previous_response is not None
                    and not strict_marker
                ):
                    latest_text = await self.latest_response(page)
                    if (
                        latest_text
                        and latest_text != previous_response
                        and elapsed >= 30000
                        and len(latest_text.strip()) > 100
                    ):
                        current_text = latest_text
                        if not marker_fallback_logged:
                            logger.warning(
                                "[bold yellow]Marker was not found yet; "
                                "watching the newest changed response instead."
                                "[/bold yellow]"
                            )
                            marker_fallback_logged = True
            else:
                current_text = await self.latest_response(page)
            if strict_marker and not self.has_response_marker(current_text, marker):
                current_text = ""
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
            elapsed = max(
                elapsed + poll_interval,
                int((monotonic() - started_at) * 1000),
            )

        if previous_text and len(previous_text) > 5 and not strict_marker:
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
                    text = self.clean_response_text(
                        await elements[-1].inner_text()
                    )
                    if text and len(text) > 10:
                        return text
            except Exception:
                continue

        try:
            main_area = page.locator(
                'main, [role="main"], .chat-container'
            ).first
            if await main_area.is_visible():
                text = self.clean_response_text(
                    await main_area.inner_text()
                )
                if text and len(text) > 10:
                    return text
        except Exception:
            pass
        return ""

    async def response_by_marker(
        self, page: Page, marker: str, *, marker_at_start: bool = False,
        expected_heading: str | None = None,
    ) -> str:
        candidates = await self.response_candidates(page, marker=marker)
        # An exact request heading before the exact token is also a valid
        # first-line identity. The outgoing instruction starts with different
        # text and therefore still cannot be mistaken for the reply.
        leading = r"[\s\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]*"
        heading = rf"(?:{re.escape(expected_heading)}\s*:?\s*)?" if expected_heading else ""
        start_pattern = rf"^{leading}(?:\*\*|`{{1,3}})?{leading}{heading}\[\[\s*{re.escape(marker)}\s*\]\]"
        matching = [
            text
            for text in candidates
            if self.has_response_marker(text, marker)
            and (not marker_at_start or re.match(start_pattern, text, flags=re.IGNORECASE))
        ]
        if not matching:
            return ""
        return (max if marker_at_start else min)(matching, key=len)

    @staticmethod
    def has_response_marker(text: str, marker: str | None) -> bool:
        """Match a complete request token near the start, never a prefix."""
        if not text or not marker:
            return False
        match = re.search(
            rf"(?<![\w-]){re.escape(marker)}(?![\w-])",
            text,
            flags=re.IGNORECASE,
        )
        return match is not None and match.start() <= 500

    async def response_candidates(
        self, page: Page, *, marker: str | None = None
    ) -> list[str]:
        candidates = []
        seen = set()
        for selector in self.response_selectors():
            try:
                locator = page.locator(selector)
                if marker:
                    # Filter in the browser before reading messages. Reading
                    # a long shared chat one message at a time on every poll
                    # makes concurrent workers spend minutes on old replies.
                    locator = locator.filter(has_text=marker)
                elements = await locator.all()
                for element in elements:
                    text = self.clean_response_text(
                        await element.inner_text()
                    )
                    if text and len(text) > 10:
                        if text not in seen:
                            candidates.append(text)
                            seen.add(text)
            except Exception:
                continue
        return candidates

    @staticmethod
    def clean_response_text(text: str | None) -> str:
        if not text:
            return ""

        lines = text.strip().splitlines()
        while lines and lines[0].strip().casefold() in {
            "thoughts",
            "expand_more",
        }:
            lines.pop(0)
        return "\n".join(lines).strip()

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
