#!/usr/bin/env python
"""插件入口：仅按注册表加载插件，来源信封先落盘，再走统一 Schema 校验。

v1 的注册表没有真实连接器；--payload 用于导入已有的来源信封，不执行其中的文本。
插件在子进程运行，凭据只通过标准输入传递，异常和插件日志不直接进入输出。
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import importlib.util
import ipaddress
import json
import os
import resource
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import yaml
from _registry_lib import DEFAULT_REGISTRY, REPO_ROOT, RegistryError
from check_secrets import Report, scan_text
from new_iteration import ITERATION_ID_PATTERN
from validate_schema import validate_one

PLUGIN_REGISTRY = REPO_ROOT / "plugins/registry.yaml"
MAX_BYTES = 8 * 1024 * 1024
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
_SECRET_KEYS = {"password", "secret", "token", "api_key", "access_token", "authorization", "cookie"}


class PluginError(Exception):
    """不携带载荷或凭据的可展示错误。"""


def resolve_plugin(name: str, registry_path: Path = PLUGIN_REGISTRY) -> dict[str, Any]:
    """未知名称不猜测路径，也不扫描来源目录寻找替代插件。"""
    try:
        document = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PluginError("无法读取插件注册表；请检查 plugins/registry.yaml") from exc
    entries = document.get("plugins") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise PluginError("插件注册表的 plugins 必须是列表")
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise PluginError("插件注册项必须包含字符串 name")
        if entry["name"] in names:
            raise PluginError("插件注册表包含重复名称")
        names.add(entry["name"])
    match = next((entry for entry in entries if entry["name"] == name), None)
    if match is None:
        raise PluginError(
            "未知插件；请检查 plugins/registry.yaml。v1 不附带真实连接器；"
            "已有信封可通过 --payload <文件> --iteration <目录> 导入。"
        )
    if not isinstance(match.get("path"), str) or not isinstance(match.get("source_type"), str):
        raise PluginError("插件注册项必须包含 path 和 source_type")
    base = registry_path.resolve().parent
    path = (base / match["path"]).resolve()
    if not path.is_relative_to(base) or path.suffix != ".py" or not path.is_file():
        raise PluginError("插件 path 必须指向 plugins/ 内存在的 Python 文件")
    return {**match, "path": str(path)}


def guard_source_ref(source_ref: str) -> None:
    """拒绝携带凭据或解析至非公网地址的 URL；连接器仍须逐跳检查重定向。"""
    parts = urlsplit(source_ref)
    if not parts.scheme:
        return
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise PluginError("URL 来源只允许 http/https")
    if parts.username or parts.password or _SECRET_KEYS.intersection(parse_qs(parts.query)):
        raise PluginError("来源引用不得携带凭据；请使用注册项的 credentials_env")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise PluginError("无法安全解析来源主机") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise PluginError("URL 来源不得访问私有、回环、链路本地或其他非公网地址")


def credentials_for(entry: dict[str, Any]) -> dict[str, str]:
    mapping = entry.get("credentials_env", {})
    if not isinstance(mapping, dict):
        raise PluginError("credentials_env 必须是凭据名到环境变量名的映射")
    credentials: dict[str, str] = {}
    for key, variable in mapping.items():
        if (
            not isinstance(key, str)
            or not isinstance(variable, str)
            or not os.environ.get(variable)
        ):
            raise PluginError("插件所需环境变量缺失；请按 credentials_env 配置，勿放入命令参数")
        credentials[key] = os.environ[variable]
    return credentials


def error_envelope(source_type: str, code: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_type": source_type,
        "fetched_at": datetime.now(UTC).isoformat(),
        "error": {"code": code, "message": "来源抓取失败；请检查注册表、配置及来源可用性"},
    }


def has_secrets(value: Any, credentials: dict[str, str] | None = None, depth: int = 0) -> bool:
    """检查已知凭据值和敏感字段；不把命中内容写入错误消息。"""
    if depth > 64:
        raise PluginError("载荷嵌套过深或存在循环引用")
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                str(key).lower() in _SECRET_KEYS
                and isinstance(item, str)
                and item
                and "CHANGE_ME" not in item
            ):
                return True
            if has_secrets(item, credentials, depth + 1):
                return True
    elif isinstance(value, list):
        return any(has_secrets(item, credentials, depth + 1) for item in value)
    elif isinstance(value, str):
        if any(secret and secret in value for secret in (credentials or {}).values()):
            return True
        report = Report()
        scan_text(Path("source-payload.yaml"), value, report)
        return bool(report.problems)
    return False


def fetch_envelope(entry: dict[str, Any], source_ref: str) -> Any:
    credentials = credentials_for(entry)
    try:
        guard_source_ref(source_ref)
    except PluginError:
        return error_envelope(entry["source_type"], "unsafe_or_unavailable_source")
    request = json.dumps(
        {"path": entry["path"], "source_ref": source_ref, "credentials": credentials}
    )
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker"],
                input=request,
                stdout=output,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=CONNECT_TIMEOUT + READ_TIMEOUT,
                env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
                check=False,
            )
            output.seek(0)
            encoded = output.read(MAX_BYTES + 1)
    except subprocess.TimeoutExpired:
        return error_envelope(entry["source_type"], "fetch_timeout")
    if result.returncode or len(encoded) > MAX_BYTES:
        return error_envelope(entry["source_type"], "fetch_failed")
    try:
        envelope = json.loads(encoded)
    except (ValueError, UnicodeError):
        return error_envelope(entry["source_type"], "invalid_plugin_output")
    if has_secrets(envelope, credentials):
        return error_envelope(entry["source_type"], "credential_in_output")
    return envelope


def worker() -> int:
    """私有子进程入口；只加载父进程已解析的路径，日志丢弃，输出限制大小。"""
    try:
        # Linux/macOS 的单文件限制也约束直接写入标准输出的插件。
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))
        request = json.loads(sys.stdin.read(MAX_BYTES))
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            spec = importlib.util.spec_from_file_location("argus_source_plugin", request["path"])
            if spec is None or spec.loader is None:
                return 1
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            envelope = module.fetch(request["source_ref"], credentials=request["credentials"])
        encoded = json.dumps(envelope).encode("utf-8")
        if len(encoded) > MAX_BYTES:
            return 1
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception:
        # 原始异常可能包含 URL、响应或凭据，只向父进程传递失败状态。
        return 1


def read_payload(path: Path) -> Any:
    """原始输入及 gzip 解压后内容均受限；不允许 YAML 执行 Python 对象。"""
    if path.stat().st_size > MAX_BYTES:
        raise PluginError("载荷文件超过大小限制")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            encoded = stream.read(MAX_BYTES + 1)
    else:
        encoded = path.read_bytes()
    if len(encoded) > MAX_BYTES:
        raise PluginError("解压后载荷超过大小限制")
    try:
        return yaml.safe_load(encoded)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise PluginError("来源信封不是有效 YAML；请修复输入文件") from exc


def output_path(iteration: Path) -> Path:
    resolved = iteration.resolve()
    if resolved.parent.name != "iterations" or not ITERATION_ID_PATTERN.fullmatch(resolved.name):
        raise PluginError("--iteration 必须是 iterations/<合法 ID> 目录")
    if not (resolved / "iteration.yaml").is_file():
        raise PluginError("迭代不存在；请先通过 scripts/new_iteration.py 创建")
    raw = resolved / "00-raw"
    if not raw.is_dir() or raw.is_symlink():
        raise PluginError("迭代的 00-raw 必须是已有的真实目录")
    return raw / "source-payload.yaml"


def persist_then_validate(envelope: Any, path: Path) -> list[str]:
    """保留无效信封供排查；已有来源不可覆盖，字节相同的重入只做校验。"""
    if has_secrets(envelope):
        raise PluginError("载荷含疑似凭据，已拒绝落盘；请先脱敏")
    try:
        encoded = yaml.safe_dump(envelope, allow_unicode=True, sort_keys=False).encode("utf-8")
    except (yaml.YAMLError, ValueError) as exc:
        raise PluginError("插件返回值无法序列化为 YAML") from exc
    if len(encoded) > MAX_BYTES:
        raise PluginError("序列化后载荷超过大小限制")
    if path.is_symlink():
        raise PluginError("隔离文件不得是符号链接")
    if path.exists():
        if path.read_bytes() != encoded:
            raise PluginError("来源信封已存在且内容不同；请按 reopen 流程处理，不自动覆盖")
    else:
        with path.open("xb") as stream:
            stream.write(encoded)
    failures = validate_one(path, DEFAULT_REGISTRY)
    # Schema 已表达互斥变体；这里保留语义门禁，避免未来换用旧注册表或
    # validator 实现时把缺少 content/error 的空信封误报为成功。
    if isinstance(envelope, dict) and ("content" in envelope) == ("error" in envelope):
        failures.append("来源信封必须且只能包含 content 或 error 其中之一")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("name", nargs="?", help="注册表中的插件名称")
    parser.add_argument("source_ref", nargs="?", help="来源引用，不得包含凭据")
    parser.add_argument("--iteration", type=Path, help="已创建的 iterations/<id> 目录")
    parser.add_argument("--payload", type=Path, help="导入现成 YAML 信封（也支持 .gz）")
    parser.add_argument("--registry", type=Path, default=PLUGIN_REGISTRY)
    args = parser.parse_args(argv)
    try:
        if args.payload is not None:
            if args.name or args.source_ref:
                raise PluginError("--payload 导入与插件抓取不可混用")
            entry = None
        elif args.name and args.source_ref:
            entry = resolve_plugin(args.name, args.registry)
        else:
            raise PluginError("请指定 <插件名> <来源引用>，或 --payload <信封文件>")
        if args.iteration is None:
            raise PluginError("请提供 --iteration iterations/<id>")
        path = output_path(args.iteration)
        if args.payload is not None:
            envelope = read_payload(args.payload)
        else:
            if entry is None:
                raise PluginError("插件抓取未解析出注册项")
            envelope = fetch_envelope(entry, args.source_ref)
        failures = persist_then_validate(envelope, path)
        if (
            entry is not None
            and isinstance(envelope, dict)
            and envelope.get("source_type") != entry["source_type"]
        ):
            failures.append("at 'source_type': 返回来源类型与注册项不一致")
        if failures:
            for failure in failures:
                print(f"error: {failure}", file=sys.stderr)
            return 1
        if isinstance(envelope, dict) and "error" in envelope:
            print(f"run_plugin: 失败信封已保存并通过结构校验：{path}", file=sys.stderr)
            return 1
        print(f"run_plugin: 信封已保存并通过校验：{path}")
        return 0
    except (PluginError, RegistryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, EOFError, ValueError, RecursionError):
        print("error: 来源文件、隔离目录或配置无法安全读取；未完成导入", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(worker() if sys.argv[1:] == ["--worker"] else main())
