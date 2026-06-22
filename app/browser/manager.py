from playwright.async_api import async_playwright, BrowserContext
from app.config.settings import settings
from app.utils.logger import logger
import os

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.context: BrowserContext = None

    async def start(self, profile_name: str = "default") -> BrowserContext:
        logger.info(f"[bold cyan]Starting Playwright browser for profile: '{profile_name}'...[/bold cyan]")
        self.playwright = await async_playwright().start()
        
        # Ensure browser data dir exists for this specific profile
        profile_dir = settings.BROWSER_DATA_DIR / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=settings.HEADLESS,
            channel="chrome",  # Using system chrome often helps with Google logins
            args=["--disable-blink-features=AutomationControlled"],
            ignore_https_errors=True
        )
        
        logger.info("[bold green]Browser started successfully.[/bold green]")
        return self.context

    async def stop(self):
        if self.context:
            logger.info("[bold yellow]Closing browser...[/bold yellow]")
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("[bold green]Browser closed.[/bold green]")
