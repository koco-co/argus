"""由 test-fixture-ui-e2e/C0001 生成的有效折扣 Web 用例。"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0001"),
    pytest.mark.iteration("test-fixture-ui-e2e"),
]


def test_apply_valid_discount(page: Page, seed_registry: dict[str, Any]) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    expect(product.cart_count()).to_be_visible()
    cart.open()
    code = seed_registry["discount_argus10"]["value"]
    price = seed_registry["product_price_eur"]["value"]
    percentage = seed_registry["discount_argus10"]["percentage"]
    expected_total = price * (100 - percentage) / 100
    cart.apply_promotion(code)
    expect(cart.promotion(code)).to_be_visible()
    expect(cart.total(f"€{expected_total:.2f}")).to_be_visible()
