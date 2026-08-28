#!/usr/bin/env python
"""加载、检查及组装 Argus 环境配置（ARCHITECTURE §7.1）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, SecretStr

REPO_ROOT = Path(__file__).resolve().parents[2]
_POSTGRES_SCHEMES = {"postgres", "postgresql"}
_READ_ONLY_COMMENT = re.compile(r"(?im)^\s*#.*(?:read[- ]?only|select[- ]?only|只读|仅.*select)")


class AuthConfig(BaseModel):
    """可选的登录凭据。"""

    username: str
    password: SecretStr


class DBConfig(BaseModel):
    """只读数据库连接信息。"""

    dsn: SecretStr


class EnvConfig(BaseModel):
    """单一执行环境的已校验配置。"""

    base_url: str
    auth: AuthConfig | None = None
    db: DBConfig | None = None
    cookies: dict[str, str] = Field(default_factory=dict)


def resolve_env_name(cli_flag: str | None = None) -> str:
    """按 CLI > TEST_ENV > local 的顺序解析环境名。"""

    return cli_flag or os.environ.get("TEST_ENV") or "local"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在；请复制 config/env.example.yaml")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} 顶层必须是映射")
    return loaded


def _put_nested(data: dict[str, Any], section: str, key: str, value: str | None) -> None:
    if value is None:
        return
    nested = data.setdefault(section, {})
    if not isinstance(nested, dict):
        nested = {}
        data[section] = nested
    nested[key] = value


def apply_environment_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """将 CI 安全注入的环境变量覆盖到同形 YAML 字段。"""

    merged = dict(data)
    base_url = os.environ.get("ARGUS_BASE_URL")
    if base_url is not None:
        merged["base_url"] = base_url
    _put_nested(merged, "auth", "username", os.environ.get("ARGUS_AUTH_USERNAME"))
    _put_nested(merged, "auth", "password", os.environ.get("ARGUS_AUTH_PASSWORD"))
    _put_nested(merged, "db", "dsn", os.environ.get("ARGUS_DB_DSN"))
    cookies = os.environ.get("ARGUS_COOKIES_JSON")
    if cookies is not None:
        parsed = json.loads(cookies)
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
        ):
            raise ValueError("ARGUS_COOKIES_JSON 必须是字符串键值对象")
        merged["cookies"] = parsed
    return merged


def load_path(path: Path) -> EnvConfig:
    """从明确路径加载配置；环境变量仍拥有最高的数据值优先级。"""

    return EnvConfig.model_validate(apply_environment_overrides(_read_yaml(path)))


def load_env(
    env_name: str | None = None,
    *,
    cli_flag: str | None = None,
    config_dir: Path | None = None,
) -> EnvConfig:
    """加载命名环境；保留 ``env_name`` 参数以兼容调用方。"""

    selected = resolve_env_name(cli_flag or env_name)
    root = config_dir or REPO_ROOT / "config"
    return load_path(root / f"env.{selected}.yaml")


def _text(data: dict[str, Any], section: str, key: str) -> str:
    value = data.get(section)
    if not isinstance(value, dict):
        return ""
    field = value.get(key)
    return field.strip() if isinstance(field, str) else ""


def _api_branch(iteration_dir: Path | None) -> bool:
    if iteration_dir is None:
        return False
    document = _read_yaml(iteration_dir / "iteration.yaml")
    branches = document.get("branches")
    return bool(isinstance(branches, dict) and branches.get("api") is True)


def check_path(path: Path, iteration_dir: Path | None = None) -> list[str]:
    """返回全部机械错误；空列表即 M8 检查通过。"""

    try:
        raw = _read_yaml(path)
        data = apply_environment_overrides(raw)
    except (FileNotFoundError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        return [str(exc)]

    problems: list[str] = []
    base_url = data.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        problems.append("base_url: 缺失")
    else:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            problems.append("base_url: 必须是 http 或 https URL")
        elif "CHANGE_ME" in base_url:
            problems.append("base_url: 仍是占位值")

    requires_credentials = _api_branch(iteration_dir)
    auth = data.get("auth")
    if requires_credentials or auth is not None:
        if not _text(data, "auth", "username"):
            problems.append("auth.username: 缺失")
        if not _text(data, "auth", "password"):
            problems.append("auth.password: 缺失")

    db = data.get("db")
    if requires_credentials or db is not None:
        dsn = _text(data, "db", "dsn")
        parsed_dsn = urlparse(dsn)
        if (
            not dsn
            or parsed_dsn.scheme not in _POSTGRES_SCHEMES
            or not parsed_dsn.hostname
            or not parsed_dsn.path.strip("/")
        ):
            problems.append("db.dsn: 必须是 PostgreSQL DSN")
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        if not _READ_ONLY_COMMENT.search(source):
            problems.append("db.dsn: 配置文件必须用注释声明只读角色")

    cookies = data.get("cookies", {})
    if not isinstance(cookies, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in cookies.items()
    ):
        problems.append("cookies: 必须是字符串键值对象")
    return problems


def _plain_document(config: EnvConfig) -> dict[str, Any]:
    document: dict[str, Any] = {"base_url": config.base_url}
    if config.auth is not None:
        document["auth"] = {
            "username": config.auth.username,
            "password": config.auth.password.get_secret_value(),
        }
    if config.db is not None:
        document["db"] = {"dsn": config.db.dsn.get_secret_value()}
    document["cookies"] = config.cookies
    return document


def assemble(env_name: str, config_dir: Path) -> Path:
    """仅在进程内从环境变量组装 gitignored 配置，避免 shell 回显密钥。"""

    target = config_dir / f"env.{env_name}.yaml"
    seed = _read_yaml(target) if target.exists() else {}
    config = EnvConfig.model_validate(apply_environment_overrides(seed))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(_plain_document(config), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    target.chmod(0o600)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="检查 M8 环境配置")
    check.add_argument("--env", dest="env_name")
    check.add_argument("--config-dir", type=Path, default=REPO_ROOT / "config")
    check.add_argument("--iteration", type=Path)

    make = subparsers.add_parser("assemble", help="从环境变量安全组装配置")
    make.add_argument("--env", dest="env_name", required=True)
    make.add_argument("--config-dir", type=Path, default=REPO_ROOT / "config")
    args = parser.parse_args(argv)

    if args.command == "assemble":
        target = assemble(args.env_name, args.config_dir)
        print(f"settings assemble: 已写入 {target}（敏感值不回显）")
        return 0

    selected = resolve_env_name(args.env_name)
    path = args.config_dir / f"env.{selected}.yaml"
    problems = check_path(path, args.iteration)
    for problem in problems:
        print(f"配置错误: {problem}", file=sys.stderr)
    if problems:
        print(f"settings check: {len(problems)} 项错误", file=sys.stderr)
        return 1
    print(f"settings check: {selected} 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
