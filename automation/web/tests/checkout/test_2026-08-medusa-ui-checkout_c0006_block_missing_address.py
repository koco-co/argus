"""由正式 UI iteration C0006 生成：缺少必填地址时阻止下单。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.checkout_page import CheckoutPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0006"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_block_missing_address(
    page: Page,
    guest_address: dict[str, str],
) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    checkout = CheckoutPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    cart.open()
    cart.go_to_checkout()
    checkout.fill_guest_address(guest_address, omit="first_name")
    checkout.continue_to_delivery()
    assert "step=address" in checkout.current_url()
    expect(checkout.required_field_error()).to_be_visible()
    expect(checkout.success_heading()).not_to_be_visible()
    expect(checkout.cart_count(1)).to_be_visible()
