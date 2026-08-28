"""Roadmap 7.2：通知重试、隔离和最新摘要解析。"""

from __future__ import annotations

from pathlib import Path

from shared.notify.base import Notifier
from shared.notify.dispatcher import dispatch, newest_summary, render_summary


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
