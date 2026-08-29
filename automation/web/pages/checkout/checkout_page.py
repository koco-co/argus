"""Medusa 游客结账、订单复核及确认页对象。"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Locator, Page


class CheckoutPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def fill_guest_address(self, address: dict[str, str], *, omit: str | None = None) -> None:
        # 这些输入没有稳定可用的 label；锁定版本提供唯一 testid，避免依赖脆弱的 DOM 顺序。
        fields = (
            ("first_name", "shipping-first-name-input"),
            ("last_name", "shipping-last-name-input"),
            ("address_1", "shipping-address-input"),
            ("company", "shipping-company-input"),
            ("postal_code", "shipping-postal-code-input"),
            ("city", "shipping-city-input"),
            ("province", "shipping-province-input"),
            ("email", "shipping-email-input"),
            ("phone", "shipping-phone-input"),
        )
        for name, test_id in fields:
            value = "" if name == omit else address.get(name, "")
            self.page.get_by_test_id(test_id).fill(value)
        self.page.get_by_test_id("shipping-country-select").select_option(address["country_code"])
        # Next.js 水合可能清掉水合前最先写入的值；提交前按真实 input 状态收敛一次。
        for name, test_id in fields:
            value = "" if name == omit else address.get(name, "")
            field = self.page.get_by_test_id(test_id)
            if field.input_value() != value:
                field.fill(value)

    def continue_to_delivery(self) -> None:
        self.page.get_by_role("button", name="Continue to delivery").click()

    def choose_standard_shipping(self) -> None:
        self.page.wait_for_url(re.compile(r"[?&]step=delivery(?:&|$)"))
        self.page.get_by_text(re.compile(r"Standard Shipping"), exact=False).first.click()
        self.page.get_by_role("button", name="Continue to payment").click()

    def choose_manual_payment(self) -> None:
        self.page.get_by_text("Manual Payment", exact=False).first.click()
        self.page.get_by_role("button", name="Continue to review").click()

    def place_order(self) -> None:
        self.page.get_by_role("button", name="Place order").click()
        # Medusa 的 server action 先返回 NEXT_REDIRECT，再异步渲染确认页；等待真实路由和成功标题，
        # 避免在确认页尚未完成流式渲染时读取到 Checkout 的中间状态。
        self.page.wait_for_url(
            re.compile(r"/order/[^/]+/confirmed(?:\?.*)?$"),
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        self.success_heading().wait_for(state="visible", timeout=30_000)

    def complete_guest_checkout(self, address: dict[str, str]) -> None:
        self.fill_guest_address(address)
        self.continue_to_delivery()
        self.choose_standard_shipping()
        self.choose_manual_payment()
        self.place_order()

    def success_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Your order was placed successfully.")

    def order_number(self) -> Locator:
        return self.page.get_by_text(re.compile(r"Order number"), exact=False)

    def shipping_summary(self) -> Locator:
        return self.page.get_by_text(re.compile(r"Standard Shipping"), exact=False).last

    def payment_summary(self) -> Locator:
        return self.page.get_by_text("Manual Payment", exact=False).last

    def item_summary(self) -> Locator:
        return self.page.get_by_text("Variant: S / Black", exact=True)

    def cart_count(self, count: int) -> Locator:
        if count == 0:
            return self.page.get_by_text("Cart (0)", exact=True)
        return self.page.get_by_text(f"{count}x", exact=True)

    def required_field_error(self) -> Locator:
        # HTML 原生必填提示气泡不进入 DOM 文本树，以 :invalid 锁定真实校验状态。
        return self.page.locator("input:invalid").first

    def current_url(self) -> str:
        return self.page.url

    def capture(self, path: Path, *, full_page: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.screenshot(path=path, full_page=full_page)
