"""由 Medusa Store API 规范生成的 Pydantic 模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.fields import Field


class CalculatedPrice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    calculated_amount: float
    currency_code: str


class ProductVariant(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    calculated_price: CalculatedPrice


class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    handle: str
    variants: list[ProductVariant]


class ProductListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    products: list[Product]


class Cart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    total: float
    subtotal: float
    discount_total: float = 0


class CartResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cart: Cart


class ApplyPromotionsRequest(BaseModel):
    promo_codes: list[str]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    message: str


class _ApiModel(BaseModel):
    """允许 Medusa 扩展 fields，同时严格校验规范声明的字段。"""

    model_config = ConfigDict(extra="ignore")


class ApiCalculatedPrice(_ApiModel):
    calculated_amount: float
    currency_code: str


class ApiProductVariant(_ApiModel):
    id: str
    title: str
    sku: str
    calculated_price: ApiCalculatedPrice


class ApiProduct(_ApiModel):
    id: str
    handle: str
    variants: list[ApiProductVariant]


class ApiProductListResponse(_ApiModel):
    products: list[ApiProduct]
    count: int
    offset: int
    limit: int


class ApiAddress(_ApiModel):
    first_name: str
    last_name: str
    address_1: str
    city: str
    postal_code: str
    country_code: str
    phone: str | None = None


class ApiCreateCartRequest(_ApiModel):
    region_id: str


class ApiAddLineItemRequest(_ApiModel):
    variant_id: str
    quantity: int


class ApiApplyPromotionsRequest(_ApiModel):
    promo_codes: list[str]


class ApiUpdateCartRequest(_ApiModel):
    email: str
    shipping_address: ApiAddress
    billing_address: ApiAddress


class ApiAddShippingMethodRequest(_ApiModel):
    option_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class ApiCreatePaymentCollectionRequest(_ApiModel):
    cart_id: str


class ApiInitializePaymentSessionRequest(_ApiModel):
    provider_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class ApiMissingProviderPaymentSessionRequest(_ApiModel):
    """负向用例发送缺少 provider_id 的初始化请求。"""

    data: dict[str, Any] = Field(default_factory=dict)


class ApiInvalidCreateCartRequest(_ApiModel):
    """负向用例允许发送不存在的地区。"""

    region_id: str | None = None


class ApiMissingVariantLineItemRequest(_ApiModel):
    """负向用例发送缺少变体 ID 的请求。"""

    quantity: int = 1


class ApiMalformedPromotionRequest(_ApiModel):
    """兼容既有 fixture 的非法字段请求。"""

    code: str


class ApiInvalidUpdateCartRequest(_ApiModel):
    """负向用例允许发送非法邮箱。"""

    email: str | None = None


class ApiMissingCartIdPaymentCollectionRequest(_ApiModel):
    """负向用例发送空支付集合请求。"""

    pass


class ApiCartItem(_ApiModel):
    id: str
    variant_id: str
    quantity: int
    unit_price: float
    title: str | None = None


class ApiCartShippingMethod(_ApiModel):
    id: str
    shipping_option_id: str


class ApiShippingMethod(_ApiModel):
    id: str
    shipping_option_id: str
    name: str


class ApiCart(_ApiModel):
    id: str
    region_id: str
    currency_code: str
    items: list[ApiCartItem]
    subtotal: float
    discount_total: float
    shipping_total: float = 0
    total: float
    email: str | None = None
    shipping_address: ApiAddress | None = None
    billing_address: ApiAddress | None = None
    shipping_methods: list[ApiCartShippingMethod] = Field(default_factory=list)


class ApiCartResponse(_ApiModel):
    cart: ApiCart


class ApiErrorResponse(_ApiModel):
    type: str
    message: str


class ApiShippingOption(_ApiModel):
    id: str
    name: str
    amount: float
    provider_id: str
    price_type: str | None = None


class ApiShippingOptionListResponse(_ApiModel):
    shipping_options: list[ApiShippingOption]


class ApiPaymentSession(_ApiModel):
    provider_id: str
    status: str
    amount: float
    currency_code: str


class ApiPaymentCollection(_ApiModel):
    id: str
    amount: float
    currency_code: str
    payment_sessions: list[ApiPaymentSession]


class ApiPaymentCollectionResponse(_ApiModel):
    payment_collection: ApiPaymentCollection


class ApiOrderItem(_ApiModel):
    id: str
    variant_id: str
    variant_sku: str
    quantity: int
    unit_price: float
    total: float


class ApiOrderPaymentCollection(_ApiModel):
    id: str
    status: str
    amount: float
    currency_code: str


class ApiOrder(_ApiModel):
    id: str
    status: str
    email: str
    items: list[ApiOrderItem]
    shipping_methods: list[ApiShippingMethod]
    payment_collections: list[ApiOrderPaymentCollection]
    subtotal: float
    discount_total: float
    total: float


class ApiOrderResponse(_ApiModel):
    type: str
    order: ApiOrder
