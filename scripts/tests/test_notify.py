"""Roadmap 7.2：通知重试、隔离和最新摘要解析。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from shared.notify.base import Notifier
from shared.notify.dispatcher import dispatch, load_config, newest_summary, render_summary
from shared.notify.email import EmailNotifier
from shared.notify.webhook import WebhookNotifier


def test_notify_script_entrypoint_imports_shared_package() -> None:
    """文档和 CI 使用脚本路径调用时，仓库根包仍必须可导入。"""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/notify.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_notify_config_is_an_explicit_noop(tmp_path: Path) -> None:
    """尚未配置真实渠道时，CI 仍应执行通知器而不是抛出 traceback。"""
    assert load_config(tmp_path / "missing.yaml") == {"channels": {}}


def test_regression_workflow_does_not_notify_a_stale_summary_without_junit() -> None:
    """环境启动失败且没有 JUnit 时，必须发送 job 状态而非旧 iteration 摘要。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/regression.yml").read_text(encoding="utf-8")
    assert "hashFiles('reports/junit.xml') != ''" in workflow
    assert "hashFiles('reports/junit.xml') == ''" in workflow
    assert "scripts/notify.py --job e2e" in workflow


class _Fake(Notifier):
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def send(self, message: str) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("故意失败")
        assert "Argus" in message


def test_failing_channel_does_not_block_sibling_and_retries_three_times() -> None:
    bad = _Fake(failures=99)
    good = _Fake(failures=1)
    sleeps: list[float] = []
    result = dispatch("Argus 结果", {"bad": bad, "good": good}, sleeper=sleeps.append)
    assert result == {"bad": False, "good": True}
    assert bad.calls == 3
    assert good.calls == 2
    assert sleeps == [1.0, 2.0, 1.0]


def test_newest_summary_uses_run_evidence_tree(tmp_path: Path) -> None:
    first = tmp_path / "one/runs/run-1/run-summary.yaml"
    second = tmp_path / "two/runs/run-2/run-summary.yaml"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("status: failed\n", encoding="utf-8")
    second.write_text("status: passed\n", encoding="utf-8")
    second.touch()
    assert newest_summary(tmp_path) == second


def test_render_summary_supports_flaky_suspect_classification() -> None:
    text = render_summary(
        {
            "iteration_id": "api-orders",
            "run_id": "run-20260828T120000Z",
            "status": "passed",
            "modules": ["orders"],
            "attempts": [{"result": "pass"}],
        },
        "flaky-suspect",
    )
    assert "状态: flaky-suspect" in text
    assert "尝试次数: 1" in text


class _WebhookResponse:
    content = b"{}"

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.body


class _WebhookClient:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, *, json: dict[str, Any]) -> _WebhookResponse:
        self.calls.append((url, json))
        return _WebhookResponse(self.body)


def test_webhook_adapters_render_channel_specific_payloads() -> None:
    """飞书与钉钉/企业微信必须使用各自真实文本信封。"""
    for channel, expected in {
        "feishu": {"msg_type": "text", "content": {"text": "Argus 结果"}},
        "dingtalk": {"msgtype": "text", "text": {"content": "Argus 结果"}},
        "wecom": {"msgtype": "text", "text": {"content": "Argus 结果"}},
    }.items():
        client = _WebhookClient({"code": 0})
        WebhookNotifier(channel, "https://notify.invalid", client=cast(Any, client)).send(
            "Argus 结果"
        )
        assert client.calls == [("https://notify.invalid", expected)]


def test_webhook_business_error_is_not_treated_as_delivery() -> None:
    client = _WebhookClient({"errcode": 40035})
    with pytest.raises(RuntimeError, match="40035"):
        WebhookNotifier("dingtalk", "https://notify.invalid", client=cast(Any, client)).send(
            "Argus 结果"
        )


def test_email_adapter_logs_in_and_sends_message(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    class _SMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls.append(("connect", (host, port, timeout)))

        def __enter__(self) -> _SMTP:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            calls.append(("login", (username, password)))

        def send_message(self, message: Any) -> None:
            calls.append(("send", (message["To"], message.get_content().strip())))

    monkeypatch.setattr("shared.notify.email.smtplib.SMTP_SSL", _SMTP)
    EmailNotifier(
        {
            "smtp_host": "smtp.invalid",
            "smtp_port": 465,
            "username": "argus@example.invalid",
            "password": "secret",
            "to": ["qa@example.invalid"],
        }
    ).send("Argus 结果")
    assert calls == [
        ("connect", ("smtp.invalid", 465, 10)),
        ("login", ("argus@example.invalid", "secret")),
        ("send", ("qa@example.invalid", "Argus 结果")),
    ]
