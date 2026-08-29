#!/usr/bin/env python
"""在真实合并后记录 release 上的 merged 状态与 GitHub 事实。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
from _writers import WriterError, load_iteration, record_event
from check_coverage import main as coverage_main
from validate_iteration import IterationReport, check_iteration

REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[a-f0-9]{40}$")
_RELEASE_BRANCH = "release"
_API_VERSION = "2022-11-28"


def verify_github_merge(
    merge_sha: str,
    pr_number: int,
    *,
    repo: str | None = None,
    token: str | None = None,
    api_url: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """核验 GitHub PR 的真实 merged 状态、目标分支和 merge SHA。"""
    repository = repo or os.environ.get("GITHUB_REPOSITORY")
    access_token = token or os.environ.get("GITHUB_TOKEN")
    if not repository:
        raise WriterError("缺少 GITHUB_REPOSITORY，不能核验真实 GitHub merge 事实")
    if client is None and not access_token:
        raise WriterError("缺少 GITHUB_TOKEN，不能核验真实 GitHub merge 事实")
    endpoint = (api_url or os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }

    def inspect(http_client: Any) -> dict[str, Any]:
        try:
            response = http_client.get(f"/repos/{repository}/pulls/{pr_number}")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise WriterError(f"GitHub PR 事实查询失败：HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise WriterError(f"GitHub PR 事实查询失败：{type(exc).__name__}") from None
        if not isinstance(payload, dict):
            raise WriterError("GitHub PR 事实响应不是对象")
        merged = payload.get("merged")
        if not isinstance(merged, bool) or not merged:
            raise WriterError(f"PR #{pr_number} 尚未被 GitHub 标记为 merged")
        base = payload.get("base")
        if not isinstance(base, dict) or base.get("ref") != _RELEASE_BRANCH:
            raise WriterError(f"PR #{pr_number} 的目标分支不是 {_RELEASE_BRANCH}")
        if payload.get("merge_commit_sha") != merge_sha:
            raise WriterError("GitHub PR 的 merge_commit_sha 与输入 merge SHA 不一致")
        if not payload.get("merged_at"):
            raise WriterError(f"PR #{pr_number} 缺少 merged_at，merge 事实不完整")
        return payload

    if client is not None:
        return inspect(client)
    try:
        with httpx.Client(
            base_url=endpoint,
            headers=headers,
            timeout=15,
            trust_env=False,
        ) as owned_client:
            return inspect(owned_client)
    except httpx.HTTPError as exc:
        raise WriterError(f"GitHub PR 事实查询失败：{type(exc).__name__}") from None


def finalize(
    iteration_dir: Path,
    merge_sha: str,
    pr_number: int,
    *,
    github_client: Any | None = None,
) -> None:
    if not _SHA.fullmatch(merge_sha):
        raise WriterError("merge SHA 必须是 40 位小写十六进制")
    if pr_number < 1:
        raise WriterError("PR number 必须为正整数")
    report = IterationReport()
    check_iteration(iteration_dir, report)
    if report.errors:
        raise WriterError("合并前 iteration 验证失败：" + "; ".join(report.errors))
    _, document = load_iteration(iteration_dir)
    if document.get("state") != "accepted":
        raise WriterError("只有 accepted 终态的 iteration 才能执行合并收口")
    coverage_status = coverage_main([str(iteration_dir), "--tier", "from-iteration"])
    if coverage_status != 0:
        raise WriterError("合并前分支覆盖链校验失败")
    verify_github_merge(merge_sha, pr_number, client=github_client)
    record_event(
        iteration_dir,
        "accepted",
        "merged",
        "script",
        merge_sha=merge_sha,
        pr_number=pr_number,
        allow_merge=True,
    )


def commit_finalization(iteration_dir: Path) -> None:
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if branch != "release":
        raise WriterError(f"只能在 release 分支提交 merged 终态，当前为 {branch}")
    relative = iteration_dir.resolve().relative_to(REPO_ROOT)
    subprocess.run(["git", "add", str(relative / "iteration.yaml")], cwd=REPO_ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"🔧 chore: 记录 {iteration_dir.name} 合并终态"],
        cwd=REPO_ROOT,
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path)
    parser.add_argument("--merge-sha", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--commit", action="store_true", help="在 release 上创建收口提交")
    args = parser.parse_args(argv)
    try:
        finalize(args.iteration, args.merge_sha, args.pr_number)
        if args.commit:
            commit_finalization(args.iteration)
    except (WriterError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"finalize_merge error: {exc}", file=sys.stderr)
        return 1
    print(f"finalize_merge: {args.iteration.name} -> merged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
