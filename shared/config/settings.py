#!/usr/bin/env python
"""加载、检查及组装 Argus 环境配置（ARCHITECTURE §7.1）。"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml  # pyright: ignore[reportMissingModuleSource]
from argus_core.parsing import load_json, load_yaml  # pyright: ignore[reportMissingImports]
from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_POSTGRES_SCHEMES = {"postgres", "postgresql"}
_ENV_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_READ_ONLY_COMMENT = re.compile(r"(?im)^\s*#.*(?:read[- ]?only|select[- ]?only|只读|仅.*select)")
_MAX_URL_UNQUOTE_PASSES = 8


def _decoded_path(value: str) -> str:
    decoded = value
    for _ in range(_MAX_URL_UNQUOTE_PASSES):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    raise ValueError("URL contains excessive encoding")


def _has_raw_control_or_space(value: str) -> bool:
    return any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    )


def _valid_endpoint(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or _has_raw_control_or_space(value):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
        decoded_path = _decoded_path(parsed.path)
    except (TypeError, ValueError):
        return False
    if (
        "\x00" in value
        or "\\" in value
        or _has_raw_control_or_space(decoded_path)
        or "\x00" in decoded_path
        or "\\" in decoded_path
        or "?" in decoded_path
        or "#" in decoded_path
        or any(part == ".." for part in decoded_path.split("/"))
    ):
        return False
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and (port is None or 1 <= port <= 65535)
    )


class AuthConfig(BaseModel):
    """可选的登录凭据。"""

    model_config = ConfigDict(extra="forbid")

    username: str
    password: SecretStr


class DBConfig(BaseModel):
    """只读数据库连接信息。"""

    model_config = ConfigDict(extra="forbid")

    dsn: SecretStr


class EnvConfig(BaseModel):
    """单一执行环境的已校验配置。"""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_base_url: str | None = None
    auth: AuthConfig | None = None
    db: DBConfig | None = None
    cookies: dict[str, str] = Field(default_factory=dict, repr=False)

    @field_validator("base_url", "api_base_url")
    @classmethod
    def valid_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _valid_endpoint(value):
            raise ValueError("endpoint must be a valid http or https URL")
        return value


def resolve_env_name(cli_flag: str | None = None) -> str:
    """按 CLI > TEST_ENV > local 的顺序解析环境名。"""

    selected = cli_flag or os.environ.get("TEST_ENV") or "local"
    if not isinstance(selected, str) or not _ENV_NAME.fullmatch(selected):
        raise ValueError("环境名必须是字母、数字、下划线或短横线组成的安全名称")
    return selected


def _assert_safe_path(path: Path, *, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise ValueError(f"{label} 不得包含路径穿越: {path}")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} 不得经过符号链接: {path}")


def _read_yaml(path: Path) -> dict[str, Any]:
    _assert_safe_path(path, label="配置文件")
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(
            f"{path} 不存在或不是安全的普通文件；请复制 config/env.example.yaml"
        )
    loaded = load_yaml(path.read_bytes()) or {}
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
    api_base_url = os.environ.get("ARGUS_API_BASE_URL")
    if api_base_url is not None:
        merged["api_base_url"] = api_base_url
    _put_nested(merged, "auth", "username", os.environ.get("ARGUS_AUTH_USERNAME"))
    _put_nested(merged, "auth", "password", os.environ.get("ARGUS_AUTH_PASSWORD"))
    _put_nested(merged, "db", "dsn", os.environ.get("ARGUS_DB_DSN"))
    cookies = os.environ.get("ARGUS_COOKIES_JSON")
    if cookies is not None:
        parsed = load_json(cookies)
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
    api_value = branches.get("api") if isinstance(branches, dict) else None
    return isinstance(api_value, bool) and api_value


def check_path(path: Path, iteration_dir: Path | None = None) -> list[str]:
    """返回全部机械错误；空列表即 M8 检查通过。"""

    try:
        raw = _read_yaml(path)
        data = apply_environment_overrides(raw)
        requires_credentials = _api_branch(iteration_dir)
    except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
        return [str(exc)]

    problems: list[str] = []
    base_url = data.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        problems.append("base_url: 缺失")
    elif not _valid_endpoint(base_url):
        problems.append("base_url: 必须是 http 或 https URL")
    elif "CHANGE_ME" in base_url:
        problems.append("base_url: 仍是占位值")

    api_base_url = data.get("api_base_url")
    if api_base_url is not None:
        if not _valid_endpoint(api_base_url):
            problems.append("api_base_url: 必须是 http 或 https URL")
        elif isinstance(api_base_url, str) and "CHANGE_ME" in api_base_url:
            problems.append("api_base_url: 仍是占位值")

    auth = data.get("auth")
    if requires_credentials or auth is not None:
        if not _text(data, "auth", "username"):
            problems.append("auth.username: 缺失")
        if not _text(data, "auth", "password"):
            problems.append("auth.password: 缺失")

    db = data.get("db")
    if requires_credentials or db is not None:
        dsn = _text(data, "db", "dsn")
        try:
            parsed_dsn = urlparse(dsn)
            dsn_port = parsed_dsn.port
        except (TypeError, ValueError):
            parsed_dsn = None
            dsn_port = None
        if (
            not dsn
            or parsed_dsn is None
            or parsed_dsn.scheme not in _POSTGRES_SCHEMES
            or not parsed_dsn.hostname
            or not parsed_dsn.path.strip("/")
            or (dsn_port is not None and not 1 <= dsn_port <= 65535)
        ):
            problems.append("db.dsn: 必须是 PostgreSQL DSN")
        try:
            source = path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeError):
            source = ""
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
    if config.api_base_url is not None:
        document["api_base_url"] = config.api_base_url
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

    env_name = resolve_env_name(env_name)
    target = config_dir / f"env.{env_name}.yaml"
    _assert_safe_path(target, label="配置文件")
    seed = _read_yaml(target) if target.is_file() else {}
    config = EnvConfig.model_validate(apply_environment_overrides(seed))
    target.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(_plain_document(config), sort_keys=False, allow_unicode=True)
    if config.db is not None:
        body = "# db.dsn 必须指向仅授予 SELECT 权限的只读角色。\n" + body
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"配置文件不是安全的普通文件: {target}")
    # _assert_safe_path and the regular-file check above protect the config
    # destination from traversal and symlink replacement.
    # pi-lens-ignore: python-path-traversal
    target.write_text(body, encoding="utf-8")
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
        try:
            target = assemble(args.env_name, args.config_dir)
        except (OSError, ValueError) as exc:
            print(f"settings assemble error: {exc}", file=sys.stderr)
            return 1
        print(f"settings assemble: 已写入 {target}（敏感值不回显）")
        return 0

    try:
        selected = resolve_env_name(args.env_name)
    except ValueError as exc:
        print(f"settings check error: {exc}", file=sys.stderr)
        return 1
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
