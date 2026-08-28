"""由正式 UI iteration C0008 生成：移动边界视口视觉验收。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from automation.web.pages.checkout.cart_page import CartPage
from automation.web.pages.checkout.checkout_page import CheckoutPage
from automation.web.pages.checkout.product_page import ProductPage

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("C0008"),
    pytest.mark.iteration("2026-08-medusa-ui-checkout"),
]


def test_verify_mobile(
    page: Page,
    seed_registry: dict[str, Any],
    guest_address: dict[str, str],
) -> None:
    visual = Path("reports/visual/2026-08-medusa-ui-checkout/c0008-mobile")
    product = ProductPage(page)
    cart = CartPage(page)
    checkout = CheckoutPage(page)
    product.set_viewport(390, 844)
    product.open_tshirt()
    product.select_small_black_variant()
    expect(product.add_button()).to_be_visible()
    expect(product.add_button()).to_be_enabled()
    assert not product.has_horizontal_overflow()
    product.capture(visual / "01-product.png")
    product.add_selected_variant()
    cart.open()
    cart.apply_promotion(seed_registry["discount_argus10"]["value"])
    expect(cart.promotion_heading()).to_be_visible()
    price = seed_registry["product_price_eur"]["value"]
    percentage = seed_registry["discount_argus10"]["percentage"]
    expected_total = price * (100 - percentage) / 100
    expect(cart.total(f"€{expected_total:.2f}")).to_be_visible()
    expect(cart.checkout_link()).to_be_visible()
    assert not product.has_horizontal_overflow()
    cart.capture(visual / "02-cart.png")
    cart.go_to_checkout()
    checkout.complete_guest_checkout(guest_address)
    expect(checkout.success_heading()).to_be_visible()
    expect(checkout.order_number()).to_be_visible()
    expect(checkout.item_summary()).to_be_visible()
    expect(checkout.shipping_summary()).to_be_visible()
    expect(checkout.payment_summary()).to_be_visible()
    expect(checkout.cart_count(0)).to_be_visible()
    assert not product.has_horizontal_overflow()
    checkout.capture(visual / "03-confirmation.png")
