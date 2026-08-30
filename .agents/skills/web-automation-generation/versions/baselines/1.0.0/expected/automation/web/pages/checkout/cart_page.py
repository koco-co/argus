"""Medusa 购物车及促销码页对象。"""

from __future__ import annotations

from playwright.sync_api import Locator, Page  # pyright: ignore[reportMissingImports]


class CartPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open(self) -> None:
        self.page.goto("/dk/cart")

    def apply_promotion(self, code: str) -> None:
        # 真实 trace 显示该控件为无 button role 的可点击文本，按 locator 回退顺序使用 text。
        self.page.get_by_text("Add Promotion Code(s)", exact=True).click()
        self.page.get_by_role("textbox").fill(code)
        with self.page.expect_response(
            lambda response: response.request.method == "POST" and "/cart" in response.url,
            timeout=30_000,
        ):
            self.page.get_by_role("button", name="Apply").click()

    def promotion(self, code: str) -> Locator:
        return self.page.get_by_text(code, exact=True)

    def total(self, formatted_amount: str) -> Locator:
        summary_row = self.page.get_by_text("Total", exact=True).locator("..")
        return summary_row.get_by_text(formatted_amount, exact=True)
