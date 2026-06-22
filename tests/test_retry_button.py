import unittest

from app.services.retry_button import NotebookLMRetryButtonHandler


class FakeButton:
    def __init__(self, visible=True, enabled=True):
        self.visible = visible
        self.enabled = enabled
        self.seen = False
        self.clicks = 0

    async def is_visible(self, timeout=None):
        return self.visible

    async def is_enabled(self, timeout=None):
        return self.enabled

    async def click(self, **kwargs):
        self.clicks += 1

    async def evaluate(self, expression, arg=None):
        if "Boolean" in expression:
            return self.seen
        if "= true" in expression:
            self.seen = True
        return None


class FakeLocator:
    def __init__(self, buttons):
        self.buttons = buttons

    async def count(self):
        return len(self.buttons)

    def nth(self, index):
        return self.buttons[index]


class FakePage:
    def __init__(self, selector_map):
        self.selector_map = selector_map
        self.waits = []

    def locator(self, selector):
        return FakeLocator(self.selector_map.get(selector, []))

    async def wait_for_timeout(self, timeout_ms):
        self.waits.append(timeout_ms)


class RetryButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_stale_retry_buttons_and_clicks_newest_fresh_one(self):
        selector = NotebookLMRetryButtonHandler.RETRY_BUTTON_SELECTORS[0]
        stale = FakeButton()
        fresh = FakeButton()
        page = FakePage({selector: [stale]})
        handler = NotebookLMRetryButtonHandler(
            page,
            settle_timeout_ms=0,
        )

        await handler.ignore_existing_buttons()
        page.selector_map[selector].append(fresh)

        clicked = await handler.click_if_present()

        self.assertTrue(clicked)
        self.assertEqual(0, stale.clicks)
        self.assertEqual(1, fresh.clicks)

    async def test_skips_disabled_buttons(self):
        selector = NotebookLMRetryButtonHandler.RETRY_BUTTON_SELECTORS[0]
        enabled = FakeButton()
        disabled = FakeButton(enabled=False)
        page = FakePage({selector: [enabled, disabled]})
        handler = NotebookLMRetryButtonHandler(
            page,
            settle_timeout_ms=0,
        )

        clicked = await handler.click_if_present()

        self.assertTrue(clicked)
        self.assertEqual(1, enabled.clicks)
        self.assertEqual(0, disabled.clicks)

    async def test_respects_max_clicks(self):
        selector = NotebookLMRetryButtonHandler.RETRY_BUTTON_SELECTORS[0]
        first = FakeButton()
        second = FakeButton()
        page = FakePage({selector: [first]})
        handler = NotebookLMRetryButtonHandler(
            page,
            max_clicks=1,
            settle_timeout_ms=0,
        )

        self.assertTrue(await handler.click_if_present())
        page.selector_map[selector].append(second)

        self.assertFalse(await handler.click_if_present())
        self.assertEqual(1, first.clicks)
        self.assertEqual(0, second.clicks)


if __name__ == "__main__":
    unittest.main()
