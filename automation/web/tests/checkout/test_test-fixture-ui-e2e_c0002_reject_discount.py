"""由 test-fixture-ui-e2e/C0002 生成的无效折扣 Web 用例。"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0002"),
    pytest.mark.iteration("test-fixture-ui-e2e"),
]


def test_reject_invalid_discount(page: Page, seed_registry: dict[str, Any]) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    expect(product.cart_count()).to_be_visible()
    cart.open()
    cart.apply_promotion("INVALID10")
    price = seed_registry["product_price_eur"]["value"]
    expect(cart.total(f"€{price:.2f}")).to_be_visible()
