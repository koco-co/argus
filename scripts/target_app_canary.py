#!/usr/bin/env python
"""以真实 Medusa 数据证明 seed registry 是自动化断言的有效预言机。"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from _target_app import REPO_ROOT, ensure_runtime_env, wait_http
from target_app_seed import AdminClient, _find, _items, discounted_total

REGISTRY = REPO_ROOT / "shared/testdata/seed-registry.yaml"


class CanaryError(RuntimeError):
    """seed registry 与真实 Medusa 数据不一致。"""


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seeds = document.get("seeds")
    if not isinstance(seeds, dict):
        raise CanaryError("seed registry 缺少 seeds 映射")
    return document


def verify_oracle(
    registry: dict[str, Any], *, live_price: int | float, live_percentage: int | float
) -> Decimal:
    """同时核对预言机输入与派生结果，避免错误 seed 仍得到假绿。"""
    seeds = registry["seeds"]
    expected_price = Decimal(str(seeds["product_price_eur"]["value"]))
    expected_percentage = Decimal(str(seeds["discount_argus10"]["percentage"]))
    if expected_price != Decimal(str(live_price)):
        raise CanaryError(f"EUR 价格不一致：registry={expected_price}, live={live_price}")
    if expected_percentage != Decimal(str(live_percentage)):
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
        variant = _find(product.get("variants", []), "sku", "SHIRT-S-BLACK", "黑色 S 码变体")
        price = _find(variant.get("prices", []), "currency_code", "eur", "EUR 价格")

        promotions = _items(
            admin.get("/admin/promotions", limit=100, fields="+application_method.*"),
            "promotions",
        )
        promotion = _find(promotions, "code", "ARGUS10", "ARGUS10 优惠")
        method = promotion.get("application_method") or {}
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
    registry = load_registry()
    if args.corrupt:
        registry = deepcopy(registry)
        registry["seeds"][args.corrupt]["value"] += 1
    live_price, live_percentage = live_values()
    try:
        total = verify_oracle(
            registry,
            live_price=live_price,
            live_percentage=live_percentage,
        )
    except CanaryError as exc:
        print(f"seed 预言机 canary 失败：{exc}")
        return 1
    print(f"seed 预言机 canary 通过：{live_price} × (100-{live_percentage})% = {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
