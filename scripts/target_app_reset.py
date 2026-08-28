#!/usr/bin/env python
"""恢复幂等 seed 基线，不直接写数据库。"""

from __future__ import annotations

from _target_app import compose, healthcheck
from target_app_seed import seed


def main() -> int:
    compose(["up", "-d", "postgres", "redis", "backend"])
    seed()
    compose(["up", "-d", "--force-recreate", "storefront"])
    healthcheck(consecutive=2)
    print("Medusa 靶应用已收敛到 seed 基线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
