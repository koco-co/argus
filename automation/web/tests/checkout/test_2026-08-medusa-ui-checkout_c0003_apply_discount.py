"""由正式 UI iteration C0003 生成：实时派生有效折扣总额。"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0003"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_apply_discount(page: Page, seed_registry: dict[str, Any]) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    cart.open()
    code = seed_registry["discount_argus10"]["value"]
    price = seed_registry["product_price_eur"]["value"]
    percentage = seed_registry["discount_argus10"]["percentage"]
    expected_total = price * (100 - percentage) / 100
    cart.apply_promotion(code)
    expect(cart.promotion_heading()).to_be_visible()
    expect(cart.promotion(code)).to_be_visible()
    expect(cart.total(f"€{expected_total:.2f}")).to_be_visible()
