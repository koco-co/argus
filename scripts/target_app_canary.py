#!/usr/bin/env python
"""以真实 Medusa 数据证明 seed registry 是自动化断言的有效预言机。"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from _target_app import REPO_ROOT, _assert_safe_path, ensure_runtime_env, wait_http
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]
from target_app_seed import AdminClient, _find, _items, discounted_total

REGISTRY = REPO_ROOT / "shared/testdata/seed-registry.yaml"


class CanaryError(RuntimeError):
    """seed registry 与真实 Medusa 数据不一致。"""


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    _assert_safe_path(path, label="seed registry")
    if path.is_symlink() or not path.is_file():
        raise CanaryError("seed registry 不是安全的普通文件")
    try:
        document = load_yaml(path.read_bytes()) or {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise CanaryError("seed registry 不是安全可解析的 YAML 文档") from exc
    if not isinstance(document, dict):
        raise CanaryError("seed registry 顶层必须是映射")
    seeds = document.get("seeds")
    if not isinstance(seeds, dict):
        raise CanaryError("seed registry 缺少 seeds 映射")
    return document


def verify_oracle(
    registry: dict[str, Any], *, live_price: int | float, live_percentage: int | float
) -> Decimal:
    """同时核对预言机输入与派生结果，避免错误 seed 仍得到假绿。"""
    try:
        seeds = registry["seeds"]
        price_seed = seeds["product_price_eur"]
        discount_seed = seeds["discount_argus10"]
        expected_price = Decimal(str(price_seed["value"]))
        expected_percentage = Decimal(str(discount_seed["percentage"]))
        live_price_decimal = Decimal(str(live_price))
        live_percentage_decimal = Decimal(str(live_percentage))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise CanaryError("seed registry 或实时值的形状无效") from exc
    if not expected_price.is_finite() or not expected_percentage.is_finite():
        raise CanaryError("seed registry 不得包含非有限数值")
    if expected_price != live_price_decimal:
        raise CanaryError(f"EUR 价格不一致：registry={expected_price}, live={live_price}")
    if expected_percentage != live_percentage_decimal:
        raise CanaryError(f"折扣比例不一致：registry={expected_percentage}, live={live_percentage}")
    return discounted_total(live_price, live_percentage)


def live_values() -> tuple[int | float, int | float]:
    wait_http("http://127.0.0.1:9000/health", timeout=60)
    runtime = ensure_runtime_env()
    admin = AdminClient(runtime["ARGUS_ADMIN_EMAIL"], runtime["ARGUS_ADMIN_PASSWORD"])
    try:
        products = _items(
            admin.get(
                "/admin/products",
                limit=100,
                fields="+variants.*,+variants.prices.*",
            ),
            "products",
        )
        product = _find(products, "handle", "t-shirt", "T-Shirt 产品")
        variant = _find(_items(product, "variants"), "sku", "SHIRT-S-BLACK", "黑色 S 码变体")
        price = _find(_items(variant, "prices"), "currency_code", "eur", "EUR 价格")

        promotions = _items(
            admin.get("/admin/promotions", limit=100, fields="+application_method.*"),
            "promotions",
        )
        promotion = _find(promotions, "code", "ARGUS10", "ARGUS10 优惠")
        method = promotion.get("application_method")
        if not isinstance(method, dict):
            raise CanaryError("ARGUS10 优惠缺少有效 application_method")
        return price["amount"], method["value"]
    finally:
        admin.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corrupt",
        choices=["product_price_eur"],
        help="仅在验收测试中于内存篡改指定 seed，必须使 canary 失败",
    )
    args = parser.parse_args(argv)
    try:
        registry = load_registry()
    except CanaryError as exc:
        print(f"seed 预言机 canary 失败：{exc}")
        return 1
    if args.corrupt:
        registry = deepcopy(registry)
        registry["seeds"][args.corrupt]["value"] += 1
    try:
        live_price, live_percentage = live_values()
        total = verify_oracle(
            registry,
            live_price=live_price,
            live_percentage=live_percentage,
        )
    except Exception as exc:  # noqa: BLE001 - CLI 边界不得暴露响应或凭据
        del exc
        print("seed 预言机 canary 失败：靶应用不可用或实时值未通过安全校验")
        return 1
    print(f"seed 预言机 canary 通过：{live_price} × (100-{live_percentage})% = {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
