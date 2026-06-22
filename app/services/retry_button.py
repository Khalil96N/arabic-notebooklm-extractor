from playwright.async_api import Page

from app.utils.logger import logger


class NotebookLMRetryButtonHandler:
    """Clicks fresh NotebookLM Retry buttons while a response is generating."""

    MAX_CLICKS = 2
    RETRY_SETTLE_MS = 8000
    SEEN_PROPERTY = "__notebookLMExtractorRetrySeen"
    RETRY_BUTTON_SELECTORS = (
        'button:has-text("Retry")',
        'button:has-text("retry")',
        'button:has-text("Try again")',
        'button:has-text("try again")',
        'button[aria-label*="Retry" i]',
        'button[aria-label*="Try again" i]',
        '[role="button"]:has-text("Retry")',
        '[role="button"]:has-text("Try again")',
        'button:has-text("إعادة المحاولة")',
        'button:has-text("حاول مرة أخرى")',
        '[role="button"]:has-text("إعادة المحاولة")',
        '[role="button"]:has-text("حاول مرة أخرى")',
    )

    def __init__(
        self,
        page: Page,
        max_clicks: int = MAX_CLICKS,
        settle_timeout_ms: int = RETRY_SETTLE_MS,
    ) -> None:
        self.page = page
        self.max_clicks = max_clicks
        self.settle_timeout_ms = settle_timeout_ms
        self.click_count = 0

    async def ignore_existing_buttons(self) -> None:
        """Mark Retry buttons already on the page before the current prompt."""
        for button in await self._visible_enabled_buttons():
            await self._mark_seen(button)

    async def click_if_present(self) -> bool:
        if self.click_count >= self.max_clicks:
            return False

        buttons = await self._visible_enabled_buttons()
        for button in reversed(buttons):
            if await self._is_seen(button):
                continue

            await self._mark_seen(button)
            await button.click(force=True)
            self.click_count += 1
            logger.warning(
                "[bold yellow]NotebookLM showed a Retry button; clicked it "
                f"({self.click_count}/{self.max_clicks}).[/bold yellow]"
            )
            await self.page.wait_for_timeout(self.settle_timeout_ms)
            return True

        return False

    async def _visible_enabled_buttons(self) -> list:
        buttons = []
        for selector in self.RETRY_BUTTON_SELECTORS:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
            except Exception:
                continue

            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if (
                        await candidate.is_visible(timeout=300)
                        and await candidate.is_enabled(timeout=300)
                    ):
                        buttons.append(candidate)
                except Exception:
                    continue

        return buttons

    async def _is_seen(self, button) -> bool:
        try:
            return bool(
                await button.evaluate(
                    "(el, prop) => Boolean(el[prop])",
                    self.SEEN_PROPERTY,
                )
            )
        except Exception:
            return False

    async def _mark_seen(self, button) -> None:
        try:
            await button.evaluate(
                "(el, prop) => { el[prop] = true; }",
                self.SEEN_PROPERTY,
            )
        except Exception:
            pass
