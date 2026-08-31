#!/usr/bin/env python
"""周回归连续两次非 flaky 失败时创建或复用 GitHub 跟踪 issue。"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
from argus_core.parsing import load_json  # pyright: ignore[reportMissingImports]

ISSUE_TITLE = "[Argus] 周回归连续失败"
API_VERSION = "2022-11-28"
_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)
_CANONICAL_SERVER_URL = "https://github.com"


def has_previous_failure(runs: list[dict[str, Any]], current_run_id: int) -> bool:
    """按 API 返回顺序寻找当前 run 之前最近的已完成 schedule。"""
    for run in runs:
        run_id_value = run.get("id", 0)
        if isinstance(run_id_value, bool) or not isinstance(run_id_value, int):
            continue
        run_id = run_id_value
        if run_id == current_run_id:
            continue
        if run.get("event") != "schedule" or run.get("status") != "completed":
            continue
        return run.get("conclusion") == "failure"
    return False


def existing_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    """同一故障只维护一个打开的跟踪 issue，避免周任务刷屏。"""
    return next((issue for issue in issues if issue.get("title") == ISSUE_TITLE), None)


def _get_json(client: httpx.Client, path: str, **params: str | int) -> Any:
    response = client.get(path, params=params)
    response.raise_for_status()
    try:
        return load_json(response.content)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("GitHub API returned an unsafe JSON response") from exc


def escalate(
    client: httpx.Client,
    repo: str,
    current_run_id: int,
    server_url: str,
) -> str:
    """检查上次 schedule 并在需要时创建可去重的 issue。"""
    if not isinstance(repo, str) or not _REPOSITORY.fullmatch(repo):
        raise ValueError("GITHUB_REPOSITORY must be an owner/repository")
    if (
        isinstance(current_run_id, bool)
        or not isinstance(current_run_id, int)
        or current_run_id < 1
    ):
        raise ValueError("GITHUB_RUN_ID must be a positive integer")
    if server_url != _CANONICAL_SERVER_URL:
        raise ValueError("GITHUB_SERVER_URL must be the canonical github.com URL")
    runs_payload = _get_json(
        client,
        f"/repos/{repo}/actions/workflows/regression.yml/runs",
        event="schedule",
        per_page=10,
    )
    if not isinstance(runs_payload, dict) or not isinstance(
        runs_payload.get("workflow_runs"), list
    ):
        raise ValueError("GitHub workflow response has an invalid shape")
    runs = [run for run in runs_payload["workflow_runs"] if isinstance(run, dict)]
    if not has_previous_failure(runs, current_run_id):
        return "上一次周回归未失败，不创建 issue"

    issues_payload = _get_json(client, f"/repos/{repo}/issues", state="open", per_page=100)
    if not isinstance(issues_payload, list):
        raise ValueError("GitHub issues response has an invalid shape")
    issues = [issue for issue in issues_payload if isinstance(issue, dict)]
    opened = existing_issue(issues)
    if opened is not None:
        return "复用已有跟踪 issue"

    run_url = f"{server_url}/{repo}/actions/runs/{current_run_id}"
    response = client.post(
        f"/repos/{repo}/issues",
        json={
            "title": ISSUE_TITLE,
            "body": (
                "周计划完整回归已连续两次失败。\n\n"
                f"当前运行：{run_url}\n\n"
                "请检查 run evidence、失败分类与靶场健康状态；不要通过修改断言或"
                "放宽受保护检查掩盖失败。"
            ),
        },
    )
    response.raise_for_status()
    try:
        issue = load_json(response.content)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("GitHub issue response is not safe JSON") from exc
    if not isinstance(issue, dict):
        raise ValueError("GitHub issue response has an invalid shape")
    return "已创建跟踪 issue"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--classification", choices=("normal", "flaky-suspect", "failed"), required=True
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--run-id", type=int, default=os.environ.get("GITHUB_RUN_ID"))
    parser.add_argument(
        "--server-url", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    )
    args = parser.parse_args(argv)

    if args.classification != "failed":
        print("周回归不是连续失败候选，不创建 issue")
        return 0
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not args.repo or not args.run_id:
        print("缺少 GITHUB_TOKEN/GITHUB_REPOSITORY/GITHUB_RUN_ID，无法升级", file=sys.stderr)
        return 1

    try:
        with httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
            timeout=15,
            trust_env=False,
        ) as client:
            print(escalate(client, args.repo, args.run_id, args.server_url))
    except (httpx.HTTPError, ValueError):
        print("周回归 issue 升级失败：GitHub API 返回错误或不安全响应", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
