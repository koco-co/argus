"""Medusa 商品详情页对象。"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page


class ProductPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open_tshirt(self) -> None:
        self.page.goto("/dk/products/t-shirt")

    def select_small_black_variant(self) -> None:
        self.page.get_by_role("button", name="Black", exact=True).click()
        self.page.get_by_role("button", name="S", exact=True).click()

    def add_selected_variant(self) -> None:
        # 移动布局会同时渲染桌面与吸底按钮，只操作当前可见实例。
        # 等待 Next.js server action 完成，确保购物车 Cookie 已持久化后再允许导航。
        with self.page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and "/products/t-shirt" in response.url
                and response.ok
            )
        ):
            self.add_button().click()

    def add_small_black_tshirt(self) -> None:
        self.select_small_black_variant()
        self.add_selected_variant()

    def cart_count(self, count: int = 1) -> Locator:
        return self.page.get_by_text(f"Cart ({count})", exact=True)

    def black_variant(self) -> Locator:
        return self.page.get_by_role("button", name="Black", exact=True)

    def small_variant(self) -> Locator:
        return self.page.get_by_role("button", name="S", exact=True)

    def add_button(self) -> Locator:
        return self.page.get_by_role("button", name="Add to cart").filter(visible=True).first

    def set_viewport(self, width: int, height: int) -> None:
        self.page.set_viewport_size({"width": width, "height": height})

    def has_horizontal_overflow(self) -> bool:
        """检测当前文档是否出现超出视口的横向滚动。"""

        return bool(
            self.page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
        )

    def capture(self, path: Path, *, full_page: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path, full_page=full_page)
