#!/usr/bin/env python
"""Medusa 靶应用的锁定配置、Compose 调用和健康探测共享实现。"""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = REPO_ROOT / "target-app"
LOCK_FILE = TARGET_DIR / "medusa.lock.yaml"
COMPOSE_FILE = TARGET_DIR / "compose.yaml"
RUNTIME_ENV = TARGET_DIR / "runtime.env"
READONLY_DB_USER = "argus_readonly"
READONLY_DB_PASSWORD = "argus_readonly_local_only"
READONLY_DB_DSN = f"postgresql://{READONLY_DB_USER}:{READONLY_DB_PASSWORD}@127.0.0.1:15432/medusa"


class HarnessError(RuntimeError):
    """靶应用生命周期无法继续时抛出的可诊断错误。"""


def _assert_safe_path(path: Path, *, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise HarnessError(f"{label} 不得包含路径穿越：{path}")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise HarnessError(f"{label} 不得经过符号链接：{path}")


def load_lock(path: Path = LOCK_FILE) -> dict[str, Any]:
    """读取并检查所有会漂移的靶应用依赖都已精确锁定。"""
    _assert_safe_path(path, label="锁文件")
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"锁文件不是安全的普通文件：{path}")
    try:
        document = load_yaml(path.read_bytes()) or {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise HarnessError("锁文件不是安全可解析的 YAML 文档") from exc
    if not isinstance(document, dict):
        raise HarnessError("锁文件顶层必须是映射")
    for key in ("medusa", "storefront", "node", "postgres", "redis", "pnpm"):
        if not isinstance(document.get(key), dict):
            raise HarnessError(f"锁文件缺少 {key}")
    commit = document["medusa"].get("commit", "")
    if len(commit) != 40 or document["storefront"].get("commit") != commit:
        raise HarnessError("backend/storefront 必须锁定到同一 40 位提交")
    for key in ("node", "postgres", "redis"):
        if "@sha256:" not in str(document[key].get("image", "")):
            raise HarnessError(f"{key}.image 必须包含 OCI digest")
    return document


def _read_dotenv(path: Path) -> dict[str, str]:
    _assert_safe_path(path, label="runtime.env")
    values: dict[str, str] = {}
    if not path.exists():
        return values
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"runtime.env 不是安全的普通文件：{path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    return values


def write_runtime_env(values: dict[str, str], path: Path = RUNTIME_ENV) -> None:
    """原子性不是跨进程契约；0600 权限和不打印秘密才是本地边界。"""
    _assert_safe_path(path, label="runtime.env")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={value}\n" for key, value in sorted(values.items()))
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise HarnessError(f"runtime.env 不是安全的普通文件：{path}")
    # The destination is checked as a non-symlink path above.
    # pi-lens-ignore: python-path-traversal
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)


def ensure_runtime_env(path: Path = RUNTIME_ENV) -> dict[str, str]:
    """创建一次性本地秘密；已有文件保持稳定，保证重复 seed 可收敛。"""
    values = _read_dotenv(path)
    defaults = {
        "ARGUS_ADMIN_EMAIL": "argus-admin@example.invalid",
        "ARGUS_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "ARGUS_BOOTSTRAPPED": "false",
        "ARGUS_ENV_NAME": "local",
        "ARGUS_PUBLISHABLE_KEY": "pk_pending",
        "COOKIE_SECRET": secrets.token_hex(32),
        "JWT_SECRET": secrets.token_hex(32),
        "NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY": "pk_pending",
    }
    changed = False
    for key, value in defaults.items():
        if not values.get(key):
            values[key] = value
            changed = True
    if changed or not path.exists():
        write_runtime_env(values, path)
    else:
        path.chmod(0o600)
    return values


def compose_environment(
    lock: dict[str, Any] | None = None,
    runtime: dict[str, str] | None = None,
) -> dict[str, str]:
    """把锁文件转换为 Compose 唯一允许的版本环境。"""
    lock = lock or load_lock()
    runtime = runtime or ensure_runtime_env()
    return {
        **os.environ,
        **runtime,
        "DTC_SOURCE_URL": str(lock["medusa"]["source_url"]),
        "DTC_COMMIT": str(lock["medusa"]["commit"]),
        "NODE_IMAGE": str(lock["node"]["image"]),
        "POSTGRES_IMAGE": str(lock["postgres"]["image"]),
        "REDIS_IMAGE": str(lock["redis"]["image"]),
        "PNPM_VERSION": str(lock["pnpm"]["version"]),
    }


def compose(
    arguments: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """只在固定 Compose 项目中执行命令，避免影响机器上的其他容器。"""
    _assert_safe_path(TARGET_DIR, label="target-app directory")
    _assert_safe_path(COMPOSE_FILE, label="Compose file")
    if TARGET_DIR.is_symlink() or not TARGET_DIR.is_dir():
        raise HarnessError(f"target-app directory is not safe: {TARGET_DIR}")
    if COMPOSE_FILE.is_symlink() or not COMPOSE_FILE.is_file():
        raise HarnessError(f"Compose file is not safe: {COMPOSE_FILE}")
    command = ["docker", "compose", "-f", str(COMPOSE_FILE), *arguments]
    return subprocess.run(
        command,
        cwd=TARGET_DIR,
        env=compose_environment(),
        check=check,
        capture_output=capture_output,
        text=True,
    )


def ensure_readonly_role() -> None:
    """幂等创建靶场只读角色，并同时施加权限与事务级写保护。"""
    sql = f"""
DO $argus$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READONLY_DB_USER}') THEN
    CREATE ROLE {READONLY_DB_USER} LOGIN PASSWORD '{READONLY_DB_PASSWORD}';
  ELSE
    ALTER ROLE {READONLY_DB_USER} WITH LOGIN PASSWORD '{READONLY_DB_PASSWORD}';
  END IF;
END
$argus$;
ALTER ROLE {READONLY_DB_USER}
  WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE {READONLY_DB_USER} SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE medusa TO {READONLY_DB_USER};
GRANT USAGE ON SCHEMA public TO {READONLY_DB_USER};
REVOKE CREATE ON SCHEMA public FROM {READONLY_DB_USER};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {READONLY_DB_USER};
ALTER DEFAULT PRIVILEGES FOR ROLE medusa IN SCHEMA public
  GRANT SELECT ON TABLES TO {READONLY_DB_USER};
""".strip()
    compose(
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "medusa",
            "-d",
            "medusa",
            "-c",
            sql,
        ]
    )


def verify_readonly_role() -> None:
    """从只读角色自身视角验证 SELECT 能力，并真实证明写入被拒绝。"""
    sql = """
SELECT
  current_setting('default_transaction_read_only') = 'on',
  COALESCE(bool_and(has_table_privilege(
    current_user, format('%I.%I', schemaname, tablename), 'SELECT'
  )), false),
  COALESCE(NOT bool_or(
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'INSERT') OR
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'UPDATE') OR
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'DELETE') OR
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'TRUNCATE') OR
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'REFERENCES') OR
    has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'TRIGGER')
  ), false)
FROM pg_tables
WHERE schemaname = 'public';
""".strip()
    result = compose(
        [
            "exec",
            "-T",
            "-e",
            f"PGPASSWORD={READONLY_DB_PASSWORD}",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            READONLY_DB_USER,
            "-d",
            "medusa",
            "-At",
            "-F",
            "|",
            "-c",
            sql,
        ],
        capture_output=True,
    )
    verdict = result.stdout.strip()
    if verdict != "t|t|t":
        raise HarnessError(f"数据库只读角色验证失败：{verdict or '无结果'}")

    write_probe = compose(
        [
            "exec",
            "-T",
            "-e",
            f"PGPASSWORD={READONLY_DB_PASSWORD}",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            READONLY_DB_USER,
            "-d",
            "medusa",
            "-c",
            "CREATE TABLE public.argus_readonly_probe (id integer);",
        ],
        check=False,
        capture_output=True,
    )
    if write_probe.returncode == 0:
        compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "medusa",
                "-d",
                "medusa",
                "-c",
                "DROP TABLE IF EXISTS public.argus_readonly_probe;",
            ]
        )
        raise HarnessError("数据库只读角色实际创建了表，已清理探针并拒绝继续")
    diagnostic = f"{write_probe.stdout}\n{write_probe.stderr}".lower()
    if "read-only transaction" not in diagnostic and "permission denied" not in diagnostic:
        raise HarnessError("数据库写入探针失败原因不是只读保护")


def wait_http(url: str, *, timeout: float = 180.0) -> None:
    """等待单个 URL 可用；超时包含最后一个错误供诊断。"""
    deadline = time.monotonic() + timeout
    last_error = "尚未请求"
    # 本地回环探测不得继承系统代理，否则 SOCKS/公司代理会污染靶场结果。
    with httpx.Client(follow_redirects=True, timeout=10.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
                if response.status_code < 500:
                    return
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            # Polling backoff is intentional; the helper waits for a real service.
            # pi-lens-ignore: python-sleep-in-test
            time.sleep(2)
    raise HarnessError(f"等待 {url} 超时：{last_error}")


def healthcheck(*, consecutive: int = 2) -> None:
    """连续探测 backend、admin 和 storefront，瞬时绿不算健康。"""
    for _ in range(consecutive):
        wait_http("http://127.0.0.1:9000/health", timeout=60)
        wait_http("http://127.0.0.1:9000/app", timeout=60)
        wait_http("http://127.0.0.1:8000", timeout=120)
        # Separate consecutive health observations deliberately.
        # pi-lens-ignore: python-sleep-in-test
        time.sleep(1)
    verify_readonly_role()
