#!/usr/bin/env python
"""构建并启动锁定版本的 Medusa 全栈靶应用。"""

from __future__ import annotations

from _target_app import RUNTIME_ENV, compose, ensure_runtime_env, healthcheck, write_runtime_env


def main() -> int:
    runtime = ensure_runtime_env()
    compose(["up", "-d", "--build", "postgres", "redis"])
    # `docker compose run` 不会自动重新构建已有镜像，迁移前必须显式构建。
    compose(["build", "backend"])
    compose(
        [
            "run",
            "--rm",
            "backend",
            "pnpm",
            "--filter",
            "@dtc/backend",
            "exec",
            "medusa",
            "db:migrate",
        ]
    )
    if runtime["ARGUS_BOOTSTRAPPED"] != "true":
        # Medusa 2.19 的 db:migrate 已执行并登记 starter 的 initial-data-seed；
        # 再次显式执行会重复分配国家，破坏幂等启动。
        compose(
            [
                "run",
                "--rm",
                "backend",
                "pnpm",
                "--filter",
                "@dtc/backend",
                "exec",
                "medusa",
                "user",
                "-e",
                runtime["ARGUS_ADMIN_EMAIL"],
                "-p",
                runtime["ARGUS_ADMIN_PASSWORD"],
            ]
        )
        runtime["ARGUS_BOOTSTRAPPED"] = "true"
        write_runtime_env(runtime, RUNTIME_ENV)
    compose(["up", "-d", "backend"])
    from target_app_seed import seed

    seed()
    compose(["up", "-d", "--force-recreate", "storefront"])
    healthcheck(consecutive=2)
    print("Medusa 已启动：http://localhost:8000；Admin/API：http://localhost:9000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
