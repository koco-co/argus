"""Medusa 游客结账、订单复核及确认页对象。"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Locator, Page


class CheckoutPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def fill_guest_address(self, address: dict[str, str], *, omit: str | None = None) -> None:
        # 锁定版本在地址步骤按固定表单顺序暴露九个 textbox role，但未稳定暴露 label。
        fields = (
            "first_name",
            "last_name",
            "address_1",
            "company",
            "postal_code",
            "city",
            "province",
            "email",
            "phone",
        )
        textboxes = self.page.get_by_role("textbox")
        for index, name in enumerate(fields):
            value = "" if name == omit else address.get(name, "")
            textboxes.nth(index).fill(value)
        self.page.get_by_role("combobox").select_option(address["country_code"])

    def continue_to_delivery(self) -> None:
        self.page.get_by_role("button", name="Continue to delivery").click()

    def choose_standard_shipping(self) -> None:
        self.page.get_by_text(re.compile(r"Standard Shipping"), exact=False).first.click()
        self.page.get_by_role("button", name="Continue to payment").click()

    def choose_manual_payment(self) -> None:
        self.page.get_by_text("Manual Payment", exact=False).first.click()
        self.page.get_by_role("button", name="Continue to review").click()

    def place_order(self) -> None:
        self.page.get_by_role("button", name="Place order").click()

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
        return self.page.get_by_text("S / Black", exact=True)

    def cart_count(self, count: int) -> Locator:
        return self.page.get_by_text(f"Cart ({count})", exact=True)

    def required_field_error(self) -> Locator:
        return self.page.get_by_text(re.compile(r"required|invalid", re.IGNORECASE)).first

    def current_url(self) -> str:
        return self.page.url

    def capture(self, path: Path, *, full_page: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path, full_page=full_page)
