"""由正式 UI iteration C0002 生成：单次加购不产生重复行。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0002"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_keep_single_line(page: Page) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    expect(product.cart_count(1)).to_be_visible()
    cart.open()
    expect(cart.item_variant()).to_have_count(1)
    expect(cart.quantity_selector()).to_have_value("1")
