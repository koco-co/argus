#!/usr/bin/env python
"""周回归连续两次非 flaky 失败时创建或复用 GitHub 跟踪 issue。"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

ISSUE_TITLE = "[Argus] 周回归连续失败"
API_VERSION = "2022-11-28"


def has_previous_failure(runs: list[dict[str, Any]], current_run_id: int) -> bool:
    """按 API 返回顺序寻找当前 run 之前最近的已完成 schedule。"""
    for run in runs:
        if int(run.get("id", 0)) == current_run_id:
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
    return response.json()


def escalate(
    client: httpx.Client,
    repo: str,
    current_run_id: int,
    server_url: str,
) -> str:
    """检查上次 schedule 并在需要时创建可去重的 issue。"""
    runs_payload = _get_json(
        client,
        f"/repos/{repo}/actions/workflows/regression.yml/runs",
        event="schedule",
        per_page=10,
    )
    runs = runs_payload.get("workflow_runs", [])
    if not has_previous_failure(runs, current_run_id):
        return "上一次周回归未失败，不创建 issue"

    issues = _get_json(client, f"/repos/{repo}/issues", state="open", per_page=100)
    opened = existing_issue(issues)
    if opened is not None:
        return f"复用已有跟踪 issue：{opened.get('html_url', opened.get('number'))}"

    run_url = f"{server_url.rstrip('/')}/{repo}/actions/runs/{current_run_id}"
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
    issue = response.json()
    return f"已创建跟踪 issue：{issue.get('html_url', issue.get('number'))}"


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
    except (httpx.HTTPError, ValueError) as exc:
        print(f"周回归 issue 升级失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
