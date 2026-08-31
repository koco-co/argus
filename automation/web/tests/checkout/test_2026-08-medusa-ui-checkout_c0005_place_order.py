"""由正式 UI iteration C0005 生成：完整游客结账并创建订单。"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.checkout_page import CheckoutPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0005"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_place_order(
    page: Page,
    seed_registry: dict[str, Any],
    guest_address: dict[str, str],
) -> None:
    product = ProductPage(page)
    cart = CartPage(page)
    checkout = CheckoutPage(page)
    product.open_tshirt()
    product.add_small_black_tshirt()
    cart.open()
    cart.apply_promotion(seed_registry["discount_argus10"]["value"])
    cart.go_to_checkout()
    checkout.complete_guest_checkout(guest_address)
    expect(checkout.success_heading()).to_be_visible()
    expect(checkout.order_number()).to_be_visible()
    expect(checkout.item_summary()).to_be_visible()
    expect(checkout.shipping_summary()).to_be_visible()
    expect(checkout.payment_summary()).to_be_visible()
    expect(checkout.cart_count(0)).to_be_visible()
