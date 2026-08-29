"""由正式 UI iteration C0001 生成：游客加入目标商品。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0001"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_add_tshirt(page: Page) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    product.open_tshirt()
    expect(product.black_variant()).to_be_visible()
    expect(product.small_variant()).to_be_visible()
    product.select_small_black_variant()
    expect(product.add_button()).to_be_visible()
    expect(product.add_button()).to_be_enabled()
    product.add_selected_variant()
    expect(product.cart_count(1)).to_be_visible()
    cart.open()
    expect(cart.item_variant()).to_be_visible()
    expect(cart.quantity_selector()).to_have_value("1")
