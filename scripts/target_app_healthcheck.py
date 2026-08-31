#!/usr/bin/env python
"""连续两次验证 Medusa backend/admin/storefront 健康。"""

from __future__ import annotations

from _target_app import HarnessError, healthcheck


def main() -> int:
    try:
        healthcheck(consecutive=2)
    except HarnessError as exc:
        print(f"靶应用健康检查失败：{exc}")
        return 1
    print("靶应用健康检查通过：backend、admin、storefront 连续两次可用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
