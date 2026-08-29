"""Roadmap 7.6：合并后状态只能绑定真实格式的 SHA/PR。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def finalizer() -> Any:
    return _load_script("finalize_merge")


def _iteration(tmp_path: Path, state: str = "accepted") -> Path:
    path = tmp_path / "iterations" / "merge-case"
    path.mkdir(parents=True)
    document = {
        "schema_version": "1.0",
        "iteration_id": "merge-case",
        "state": state,
        "blocked_reason": None,
        "branches": {"ui": True, "api": False},
        "artifacts": {
            key: {"status": "not_started"}
            for key in (
                "requirements",
                "exemptions",
                "test_points",
                "functional_cases",
                "api_spec",
                "api_cases",
                "web_automation",
                "api_automation",
                "execution",
            )
        },
        "approvals": [],
        "events": [],
        "source_manifest": [],
    }
    if state == "accepted":
        # 纯写入器测试只需合法事件链；语义验证由既有 validator 测试覆盖。
        states = [
            "created",
            "requirements_clarifying",
            "requirements_accepted",
            "test_points_review",
            "test_points_accepted",
            "functional_cases_generating",
            "functional_cases_exported",
            "web_automation_generating",
            "web_automation_generated",
            "env_pending",
            "env_configured",
            "executing",
            "execution_passed",
            "acceptance_pending",
            "accepted",
        ]
        document["events"] = [
            {
                "from_state": before,
                "to_state": after,
                "timestamp": "2026-08-28T12:00:00Z",
                "triggered_by": "agent",
            }
            for before, after in zip(states, states[1:], strict=False)
        ]
        document["approvals"] = [
            {
                "stage": stage,
                "action": action,
                "actor": "user",
                "timestamp": "2026-08-28T12:00:00Z",
                "artifact_sha256": "a" * 64,
            }
            for stage, action in (
                ("requirements", "accepted"),
                ("test_points", "accepted"),
                ("exemptions", "accepted"),
                ("environment", "provided"),
                ("acceptance", "accepted"),
            )
        ]
    (path / "iteration.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    return path


def test_finalize_records_merge_metadata(
    finalizer: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _iteration(tmp_path)
    monkeypatch.setattr(finalizer, "check_iteration", lambda *args, **kwargs: None)
    monkeypatch.setattr(finalizer, "coverage_main", lambda *args, **kwargs: 0)
    monkeypatch.setattr(finalizer, "verify_github_merge", lambda *args, **kwargs: {})
    finalizer.finalize(path, "b" * 40, 42)
    document = yaml.safe_load((path / "iteration.yaml").read_text())
    assert document["state"] == "merged"
    assert document["events"][-1]["merge_sha"] == "b" * 40
    assert document["events"][-1]["pr_number"] == 42


class _GitHubResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class _GitHubClient:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.paths: list[str] = []

    def get(self, path: str) -> _GitHubResponse:
        self.paths.append(path)
        return _GitHubResponse(self.payload)


def test_verify_github_merge_requires_real_release_pr_fact(finalizer: Any) -> None:
    client = _GitHubClient(
        {
            "merged": True,
            "merged_at": "2026-08-29T10:00:00Z",
            "merge_commit_sha": "b" * 40,
            "base": {"ref": "release"},
        }
    )
    payload = finalizer.verify_github_merge(
        "b" * 40,
        42,
        repo="owner/repo",
        token="test-token",
        client=client,
    )
    assert payload["merged"] is True
    assert client.paths == ["/repos/owner/repo/pulls/42"]


def test_verify_github_merge_rejects_mismatched_fact(finalizer: Any) -> None:
    client = _GitHubClient(
        {
            "merged": True,
            "merged_at": "2026-08-29T10:00:00Z",
            "merge_commit_sha": "c" * 40,
            "base": {"ref": "release"},
        }
    )
    with pytest.raises(finalizer.WriterError, match="merge_commit_sha"):
        finalizer.verify_github_merge(
            "b" * 40,
            42,
            repo="owner/repo",
            token="test-token",
            client=client,
        )


def test_finalize_rejects_nonaccepted_and_bad_sha(finalizer: Any, tmp_path: Path) -> None:
    path = _iteration(tmp_path, state="created")
    with pytest.raises(finalizer.WriterError):
        finalizer.finalize(path, "bad", 0)


def test_finalize_rejects_nonaccepted_with_valid_metadata(
    finalizer: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """即使 SHA 和 PR 格式正确，也不得从非 accepted 终态收口。"""
    path = _iteration(tmp_path, state="created")
    monkeypatch.setattr(finalizer, "check_iteration", lambda *args, **kwargs: None)
    with pytest.raises(finalizer.WriterError, match="accepted"):
        finalizer.finalize(path, "b" * 40, 42)


def test_finalize_rejects_coverage_gap(
    finalizer: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """受保护分支收口前必须再次通过当前分支的完整覆盖链。"""
    path = _iteration(tmp_path)
    monkeypatch.setattr(finalizer, "check_iteration", lambda *args, **kwargs: None)
    monkeypatch.setattr(finalizer, "coverage_main", lambda *args, **kwargs: 1)
    with pytest.raises(finalizer.WriterError, match="覆盖链"):
        finalizer.finalize(path, "b" * 40, 42)
