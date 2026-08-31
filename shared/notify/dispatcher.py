"""通知构建、渠道注册、隔离重试与最新摘要解析。"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

from shared.notify.base import Notifier
from shared.notify.email import EmailNotifier
from shared.notify.webhook import WebhookNotifier

LOGGER = logging.getLogger("argus.notify")


def _assert_safe_path(path: Path, *, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise ValueError(f"{label} 不得包含路径穿越：{path}")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} 不得经过符号链接：{path}")


def newest_summary(iterations_dir: Path) -> Path:
    _assert_safe_path(iterations_dir, label="iterations directory")
    root = iterations_dir.resolve()
    candidates: list[Path] = []
    for candidate in iterations_dir.glob("*/runs/*/run-summary.yaml"):
        try:
            _assert_safe_path(candidate, label="run summary")
        except ValueError:
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            continue
        candidates.append(candidate)
    if not candidates:
        raise FileNotFoundError(f"{iterations_dir} 下没有安全的 run-summary.yaml")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _display_text(value: object, fallback: str) -> str:
    if isinstance(value, str) and 0 < len(value) <= 128 and "\r" not in value and "\n" not in value:
        return value
    return fallback


def render_summary(document: dict[str, Any], classification: str | None = None) -> str:
    if not isinstance(document, dict):
        raise ValueError("run summary must be an object")
    status = (
        _display_text(classification, "")
        if classification
        else _display_text(document.get("status"), "unknown")
    )
    modules_value = document.get("modules", [])
    modules = (
        [item for item in modules_value if _display_text(item, "")]
        if isinstance(modules_value, list)
        else []
    )
    attempts = document.get("attempts", [])
    attempt_count = len(attempts) if isinstance(attempts, list) else 0
    return "\n".join(
        [
            "Argus 自动化执行结果",
            f"迭代: {_display_text(document.get('iteration_id'), 'unknown')}",
            f"运行: {_display_text(document.get('run_id'), 'unknown')}",
            f"状态: {status or 'unknown'}",
            f"模块: {', '.join(modules)}",
            f"尝试次数: {attempt_count}",
        ]
    )


def build_notifiers(config: dict[str, Any]) -> dict[str, Notifier]:
    if not isinstance(config, dict):
        raise ValueError("notify 配置必须是映射")
    channels = config.get("channels", {})
    if not isinstance(channels, dict):
        raise ValueError("notify 配置 channels 必须是映射")
    result: dict[str, Notifier] = {}
    for name, values in channels.items():
        if name in {"dingtalk", "feishu", "wecom"}:
            if (
                not isinstance(values, dict)
                or not isinstance(values.get("webhook"), str)
                or not values["webhook"].strip()
            ):
                raise ValueError(f"通知渠道 {name} 缺少 webhook")
            result[name] = WebhookNotifier(name, values["webhook"])
        elif name == "email":
            if not isinstance(values, dict):
                raise ValueError("email 通知渠道必须是映射")
            required = ("smtp_host", "username", "password", "to")
            if any(not isinstance(values.get(key), str) or not values[key] for key in required[:3]):
                raise ValueError("email 通知渠道缺少 SMTP 配置")
            recipients = values.get("to")
            if not isinstance(recipients, list) or any(
                not isinstance(item, str) or not item for item in recipients
            ):
                raise ValueError("email 通知渠道 to 必须是非空字符串列表")
            port = values.get("smtp_port", 465)
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("email 通知渠道 smtp_port 无效")
            result[name] = EmailNotifier(values)
        else:
            LOGGER.warning("忽略未知通知渠道：%s", name)
    return result


def dispatch(
    message: str,
    notifiers: dict[str, Notifier],
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for name, notifier in notifiers.items():
        for index, delay in enumerate((1.0, 2.0, 4.0), start=1):
            try:
                notifier.send(message)
                results[name] = True
                break
            except Exception as exc:  # noqa: BLE001 - 渠道隔离边界必须吞并并记录所有异常
                # 不记录异常原文：HTTP 客户端可能把 webhook URL 或 SMTP 主机
                # 拼进消息，渠道配置中的凭据不能进入 CI 日志。
                LOGGER.error(
                    "通知渠道 %s 第 %d 次失败（%s）",
                    name,
                    index,
                    type(exc).__name__,
                )
                if index < 3:
                    sleeper(delay)
        else:
            results[name] = False
    return results


def load_config(path: Path, *, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """读取本地配置，并用 CI 环境变量覆盖渠道秘密。

    GitHub Actions 只把 Secrets 注入环境，不生成携密文件；空环境变量视为未配置，
    以兼容 fork PR 和尚未启用通知的仓库。
    """
    _assert_safe_path(path, label="notify 配置")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("notify 配置必须是项目指定的普通文件")
    if path.is_file():
        try:
            document = load_yaml(path.read_bytes()) or {}
        except (OSError, ValueError) as exc:
            raise ValueError("notify 配置不是安全可解析的 YAML 文档") from exc
    else:
        LOGGER.warning("通知配置不存在，尝试从环境变量装配：%s", path)
        document = {}
    if not isinstance(document, dict):
        raise ValueError("notify 配置顶层必须是映射")

    raw_channels = document.get("channels", {})
    if not isinstance(raw_channels, dict):
        raise ValueError("notify 配置 channels 必须是映射")
    channels: dict[str, dict[str, Any]] = {}
    for name, values in raw_channels.items():
        channel_name = str(name)
        if channel_name in {"dingtalk", "feishu", "wecom", "email"}:
            if not isinstance(values, dict):
                raise ValueError(f"通知渠道 {channel_name} 必须是映射")
            channels[channel_name] = dict(values)
    env = os.environ if environ is None else environ

    for channel in ("dingtalk", "feishu", "wecom"):
        key = f"ARGUS_NOTIFY_{channel.upper()}_WEBHOOK"
        if value := env.get(key, "").strip():
            channels[channel] = {"webhook": value}

    email_env = {
        "smtp_host": env.get("ARGUS_NOTIFY_EMAIL_SMTP_HOST", "").strip(),
        "smtp_port": env.get("ARGUS_NOTIFY_EMAIL_SMTP_PORT", "").strip(),
        "username": env.get("ARGUS_NOTIFY_EMAIL_USERNAME", "").strip(),
        "password": env.get("ARGUS_NOTIFY_EMAIL_PASSWORD", "").strip(),
        "to": env.get("ARGUS_NOTIFY_EMAIL_TO", "").strip(),
    }
    if any(email_env.values()):
        email = dict(channels.get("email", {}))
        for key in ("smtp_host", "username", "password"):
            if email_env[key]:
                email[key] = email_env[key]
        if email_env["smtp_port"]:
            try:
                email["smtp_port"] = int(email_env["smtp_port"])
            except ValueError as exc:
                raise ValueError("邮件通知端口必须是整数") from exc
        if email_env["to"]:
            email["to"] = [item.strip() for item in email_env["to"].split(",") if item.strip()]
        required = ("smtp_host", "username", "password", "to")
        missing = [key for key in required if not email.get(key)]
        if missing:
            raise ValueError(f"邮件通知环境变量不完整，缺少：{', '.join(missing)}")
        channels["email"] = email

    return {**document, "channels": channels}
