"""Medusa 商品详情页对象。"""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class ProductPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open_tshirt(self) -> None:
        self.page.goto("/dk/products/t-shirt")

    def add_small_black_tshirt(self) -> None:
        self.page.get_by_role("button", name="Black", exact=True).click()
        self.page.get_by_role("button", name="S", exact=True).click()
        # 移动布局会同时渲染桌面与吸底按钮，只操作当前可见实例。
        self.page.get_by_role("button", name="Add to cart").filter(visible=True).first.click()

    def cart_count(self) -> Locator:
        return self.page.get_by_text("Cart (1)", exact=True)
