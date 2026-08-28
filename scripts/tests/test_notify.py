"""Roadmap 7.2：通知重试、隔离和最新摘要解析。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from shared.notify.base import Notifier
from shared.notify.dispatcher import dispatch, load_config, newest_summary, render_summary


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
