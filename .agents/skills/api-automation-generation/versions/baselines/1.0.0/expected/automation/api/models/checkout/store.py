"""由 Medusa Store API 规范生成的 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
