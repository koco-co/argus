"""Roadmap 7.2：通知重试、隔离和最新摘要解析。"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest  # pyright: ignore[reportMissingImports]

from shared.notify import webhook as webhook_module
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
    assert load_config(tmp_path / "missing.yaml", environ={}) == {"channels": {}}


def test_notify_config_can_be_assembled_from_ci_environment(tmp_path: Path) -> None:
    """Actions Secrets 必须能通过环境变量直接装配渠道，不落盘真实值。"""
    config = load_config(
        tmp_path / "missing.yaml",
        environ={
            "ARGUS_NOTIFY_FEISHU_WEBHOOK": "https://notify.invalid/feishu",
            "ARGUS_NOTIFY_EMAIL_SMTP_HOST": "smtp.invalid",
            "ARGUS_NOTIFY_EMAIL_SMTP_PORT": "587",
            "ARGUS_NOTIFY_EMAIL_USERNAME": "argus@example.invalid",
            "ARGUS_NOTIFY_EMAIL_PASSWORD": "secret",
            "ARGUS_NOTIFY_EMAIL_TO": "qa@example.invalid, owner@example.invalid",
        },
    )
    assert config == {
        "channels": {
            "feishu": {"webhook": "https://notify.invalid/feishu"},
            "email": {
                "smtp_host": "smtp.invalid",
                "smtp_port": 587,
                "username": "argus@example.invalid",
                "password": "secret",
                "to": ["qa@example.invalid", "owner@example.invalid"],
            },
        }
    }


def test_notify_environment_overrides_file_without_discarding_sibling_channels(
    tmp_path: Path,
) -> None:
    """CI 注入值优先于本地文件，但不得删除文件中的其他完整渠道。"""
    path = tmp_path / "notify.yaml"
    path.write_text(
        "channels:\n"
        "  dingtalk:\n"
        "    webhook: https://notify.invalid/old\n"
        "  wecom:\n"
        "    webhook: https://notify.invalid/wecom\n",
        encoding="utf-8",
    )
    config = load_config(
        path,
        environ={"ARGUS_NOTIFY_DINGTALK_WEBHOOK": "https://notify.invalid/new"},
    )
    assert config["channels"] == {
        "dingtalk": {"webhook": "https://notify.invalid/new"},
        "wecom": {"webhook": "https://notify.invalid/wecom"},
    }


def test_partial_email_environment_is_rejected(tmp_path: Path) -> None:
    """不完整的 Secret 组合必须明确失败，避免把错误配置伪装为零渠道。"""
    with pytest.raises(ValueError, match="邮件通知环境变量不完整"):
        load_config(
            tmp_path / "missing.yaml",
            environ={"ARGUS_NOTIFY_EMAIL_SMTP_HOST": "smtp.invalid"},
        )


def test_only_trusted_workflow_maps_notification_secrets_to_environment() -> None:
    """通知 Secret 只能进入默认分支代码运行的可信工作流。"""
    root = Path(__file__).resolve().parents[2]
    trusted = (root / ".github/workflows/trusted-notifications.yml").read_text(encoding="utf-8")
    for name in (
        "ARGUS_NOTIFY_DINGTALK_WEBHOOK",
        "ARGUS_NOTIFY_FEISHU_WEBHOOK",
        "ARGUS_NOTIFY_WECOM_WEBHOOK",
        "ARGUS_NOTIFY_EMAIL_SMTP_HOST",
        "ARGUS_NOTIFY_EMAIL_SMTP_PORT",
        "ARGUS_NOTIFY_EMAIL_USERNAME",
        "ARGUS_NOTIFY_EMAIL_PASSWORD",
        "ARGUS_NOTIFY_EMAIL_TO",
    ):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in trusted
    for workflow_name in ("ci.yml", "regression.yml"):
        workflow = (root / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
        assert "secrets.ARGUS_NOTIFY_" not in workflow
        assert "issues: write" not in workflow
        assert "persist-credentials: false" in workflow


def test_regression_workflow_does_not_notify_a_stale_summary_without_junit() -> None:
    """e2e 只上传受限分类；可信工作流不回退到旧 iteration 摘要。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/regression.yml").read_text(encoding="utf-8")
    trusted = (root / ".github/workflows/trusted-notifications.yml").read_text(encoding="utf-8")
    assert "reports/junit-first.xml" in workflow
    assert "reports/junit-retry.xml" in workflow
    assert "reports/allure-first" in workflow
    assert "reports/allure-retry" in workflow
    assert "scripts/notify.py --summary auto" not in workflow
    assert "保存受限通知分类" in workflow
    assert '--job "$ARGUS_WORKFLOW_NAME"' in trusted
    assert '--status "$ARGUS_WORKFLOW_STATUS"' in trusted


def test_trusted_workflow_derives_nonempty_workflow_status() -> None:
    """可信通知使用 completed workflow_run 结论，并为异常事件提供 unknown。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/trusted-notifications.yml").read_text(encoding="utf-8")
    assert "github.event.workflow_run.conclusion || 'unknown'" in workflow
    assert "github.event.workflow_run.name" in workflow
    assert "job.status" not in workflow


def test_notify_job_rejects_empty_status() -> None:
    """空状态会形成误导消息，CLI 必须在分发前拒绝。"""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/notify.py"),
            "--job",
            "e2e",
            "--status",
            "",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--status 不得为空" in result.stderr


def test_e2e_workflow_exposes_manual_failure_and_flaky_scenarios() -> None:
    """7.1 的强制失败与单次 flaky 验收必须能由手工工作流重复执行。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/regression.yml").read_text(encoding="utf-8")
    assert "acceptance_scenario:" in workflow
    assert "force_failure" in workflow
    assert "force_flaky" in workflow
    assert "ARGUS_CI_ACCEPTANCE_SCENARIO" in workflow
    assert "automation/**/tests/harness/**" in (root / "scripts/orphan-allowlist.yaml").read_text(
        encoding="utf-8"
    )
    assert (root / "automation/web/tests/harness/test_ci_acceptance_control.py").is_file()


def test_static_workflow_exposes_manual_failure_scenario() -> None:
    """static-checks 必须能真实触发失败通知分支而不修改业务代码。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "force_failure:" in workflow
    assert "inputs.force_failure" in workflow
    assert "exit 1" in workflow


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


def test_dispatch_does_not_log_channel_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    """渠道异常中即使带 URL，也不能把 webhook 凭据写入日志。"""

    class _LeakingFailure(Notifier):
        def send(self, message: str) -> None:
            del message
            raise RuntimeError("https://notify.invalid/hook?token=do-not-log")

    with caplog.at_level(logging.ERROR):
        result = dispatch("Argus 结果", {"leaking": _LeakingFailure()}, sleeper=lambda _: None)

    assert result == {"leaking": False}
    assert "do-not-log" not in caplog.text
    assert "RuntimeError" in caplog.text


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
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.content = json.dumps(body).encode("utf-8")

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


def test_webhook_http_error_does_not_expose_url(caplog: pytest.LogCaptureFixture) -> None:
    request = webhook_module.httpx.Request("POST", "https://notify.invalid/hook?token=do-not-log")
    response = webhook_module.httpx.Response(403, request=request)
    client = _WebhookClient({})
    client.post = lambda url, *, json: response  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="403"):
        WebhookNotifier("dingtalk", request.url, client=cast(Any, client)).send("Argus 结果")
    assert "do-not-log" not in caplog.text


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

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: Any,
        ) -> None:
            del exc_type, exc_value, exc_traceback

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
