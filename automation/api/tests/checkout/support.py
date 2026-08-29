"""正式 API 用例共享的真实 Medusa 业务链辅助函数。"""

# ruff: noqa: I001 — 别名导入保持生成模型名称与用例语义一致。

from __future__ import annotations

from dataclasses import dataclass, replace

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import (
    ApiAddress as Address,
    ApiCart as Cart,
    ApiPaymentCollection as PaymentCollection,
    ApiProduct as Product,
    ApiProductVariant as ProductVariant,
    ApiShippingOption as ShippingOption,
    ApiUpdateCartRequest as UpdateCartRequest,
)


@dataclass(frozen=True)
class CartSetup:
    """保存由真实响应逐步构造的购物车上下文。"""

    product: Product
    variant: ProductVariant
    cart: Cart
    shipping_option: ShippingOption | None = None
    payment_collection: PaymentCollection | None = None


def select_tshirt_variant(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> tuple[Product, ProductVariant]:
    """按句柄和 SKU 从真实 Store API 响应选择商品及黑色 S 码。"""

    products = store_client.list_tshirt(seed_state["region_europe"])
    product = next(item for item in products.products if item.handle == "t-shirt")
    variant = next(item for item in product.variants if item.sku == "SHIRT-S-BLACK")
    return product, variant


def create_cart_with_line(store_client: FullStoreClient, seed_state: dict[str, str]) -> CartSetup:
    """使用运行时地区创建购物车并加入真实解析出的变体。"""

    product, variant = select_tshirt_variant(store_client, seed_state)
    created = store_client.create_cart(seed_state["region_europe"]).cart
    added = store_client.add_line_item(created.id, variant.id).cart
    return CartSetup(product=product, variant=variant, cart=added)


def guest_address() -> Address:
    """构造仅用于本地测试的虚构德国地址。"""

    return Address(
        first_name="Argus",
        last_name="API",
        address_1="Teststrasse 1",
        city="Berlin",
        postal_code="10115",
        country_code="de",
        phone="+4900000000",
    )


def update_guest_cart(
    store_client: FullStoreClient,
    setup: CartSetup,
    email: str = "argus-api@example.invalid",
) -> CartSetup:
    """写入虚构游客资料，并以 API 响应替换购物车上下文。"""

    address = guest_address()
    request = UpdateCartRequest(
        email=email,
        shipping_address=address,
        billing_address=address,
    )
    updated = store_client.update_cart(setup.cart.id, request).cart
    return replace(setup, cart=updated)


def add_standard_shipping(store_client: FullStoreClient, setup: CartSetup) -> CartSetup:
    """从真实配送选项响应选择 Standard Shipping。"""

    options = store_client.list_shipping_options(setup.cart.id).shipping_options
    standard = next(option for option in options if option.name == "Standard Shipping")
    updated = store_client.add_shipping_method(setup.cart.id, standard.id).cart
    return replace(setup, cart=updated, shipping_option=standard)


def prepare_payment_checkout(
    store_client: FullStoreClient,
    seed_state: dict[str, str],
    email: str = "argus-api@example.invalid",
) -> CartSetup:
    """准备地址、配送和 Manual Payment 会话，全部依赖真实 API 响应。"""

    setup = create_cart_with_line(store_client, seed_state)
    setup = update_guest_cart(store_client, setup, email)
    setup = add_standard_shipping(store_client, setup)
    collection = store_client.create_payment_collection(setup.cart.id).payment_collection
    initialized = store_client.initialize_payment_session(
        collection.id, seed_state["payment_manual"]
    ).payment_collection
    return replace(setup, payment_collection=initialized)
