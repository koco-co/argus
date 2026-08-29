"""由正式 UI iteration C0004 生成：无效折扣不改变总额。"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0004"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_reject_discount(page: Page, seed_registry: dict[str, Any]) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    cart.open()
    price = seed_registry["product_price_eur"]["value"]
    expect(cart.total(f"€{price:.2f}")).to_be_visible()
    cart.apply_promotion("INVALID10")
    expect(cart.promotion_heading()).not_to_be_visible()
    expect(cart.total(f"€{price:.2f}")).to_be_visible()
