"""Medusa 购物车及促销码页对象。"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page


class CartPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open(self) -> None:
        self.page.goto("/dk/cart")

    def apply_promotion(self, code: str) -> None:
        # 真实 trace 显示该控件为无 button role 的可点击文本，按 locator 回退顺序使用 text。
        self.page.get_by_text("Add Promotion Code(s)", exact=True).click()
        self.page.get_by_role("textbox").fill(code)
        self.page.get_by_role("button", name="Apply").click()

    def promotion(self, code: str) -> Locator:
        return self.page.get_by_text(code, exact=True)

    def promotion_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Promotion(s) applied:")

    def total(self, formatted_amount: str) -> Locator:
        summary_row = self.page.get_by_text("Total", exact=True).locator("..")
        return summary_row.get_by_text(formatted_amount, exact=True)

    def item_variant(self) -> Locator:
        return self.page.get_by_text("S / Black", exact=True)

    def quantity_selector(self) -> Locator:
        return self.page.get_by_role("combobox").first

    def go_to_checkout(self) -> None:
        self.page.get_by_role("link", name="Go to checkout").click()

    def checkout_link(self) -> Locator:
        return self.page.get_by_role("link", name="Go to checkout")

    def capture(self, path: Path, *, full_page: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path, full_page=full_page)
