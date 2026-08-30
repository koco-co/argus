#!/usr/bin/env python
"""在真实合并后记录 release 上的 merged 状态与 GitHub 事实。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx  # pyright: ignore[reportMissingImports]
from _writers import (
    WriterError,
    _make_merge_verification,
    load_iteration,
    record_merged_event,
)
from argus_core.parsing import load_json  # pyright: ignore[reportMissingImports]
from argus_plugin_sdk.security import (  # pyright: ignore[reportMissingImports]
    validate_response_peer,  # pyright: ignore[reportMissingImports]
)
from check_coverage import main as coverage_main
from validate_iteration import IterationReport, check_iteration

REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[a-f0-9]{40}$")
_RELEASE_BRANCH = "release"
_API_VERSION = "2022-11-28"
_MAX_GITHUB_RESPONSE_BYTES = 8 * 1024 * 1024
_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)


def _validate_github_endpoint(endpoint: str) -> None:
    if not isinstance(endpoint, str):
        raise WriterError("GitHub API URL must be the canonical api.github.com HTTPS host")
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError as exc:
        raise WriterError("GitHub API URL malformed") from exc
    if (
        endpoint != "https://api.github.com"
        or parts.scheme != "https"
        or parts.hostname != "api.github.com"
        or parts.username
        or parts.password
        or port is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise WriterError("GitHub API URL must be the canonical api.github.com HTTPS host")


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
    if not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha):
        raise WriterError("merge SHA 必须是 40 位小写十六进制")
    if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
        raise WriterError("PR number 必须为正整数")
    repository = repo if repo is not None else os.environ.get("GITHUB_REPOSITORY")
    access_token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise WriterError("GITHUB_REPOSITORY 必须是 owner/repository")
    if client is None and not access_token:
        raise WriterError("缺少 GITHUB_TOKEN，不能核验真实 GitHub merge 事实")
    raw_endpoint = (
        api_url if api_url is not None else os.environ.get("GITHUB_API_URL")
    ) or "https://api.github.com"
    if not isinstance(raw_endpoint, str):
        raise WriterError("GitHub API URL malformed")
    endpoint = raw_endpoint
    _validate_github_endpoint(endpoint)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }

    def inspect(http_client: Any) -> dict[str, Any]:
        try:
            response = http_client.get(f"/repos/{repository}/pulls/{pr_number}")
            validate_response_peer(response)
            response.raise_for_status()
            if len(response.content) > _MAX_GITHUB_RESPONSE_BYTES:
                raise WriterError("GitHub PR 事实响应超过大小限制")
            payload = load_json(response.content)
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
        response_number = payload.get("number")
        if (
            isinstance(response_number, bool)
            or not isinstance(response_number, int)
            or response_number != pr_number
        ):
            raise WriterError("GitHub PR response number does not match the requested PR")
        expected_url = f"https://github.com/{repository}/pull/{pr_number}"
        if payload.get("html_url") != expected_url:
            raise WriterError("GitHub PR response URL is not bound to the requested repository/PR")
        merged_at = payload.get("merged_at")
        if not isinstance(merged_at, str) or not merged_at:
            raise WriterError(f"PR #{pr_number} 缺少 merged_at，merge 事实不完整")
        try:
            parsed_merged_at = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        except ValueError:
            raise WriterError(f"PR #{pr_number} 的 merged_at 不是有效时间") from None
        if parsed_merged_at.tzinfo is None:
            raise WriterError(f"PR #{pr_number} 的 merged_at 必须包含时区")
        if parsed_merged_at > datetime.now(UTC):
            raise WriterError(f"PR #{pr_number} 的 merged_at 不能在未来")
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


def _confined_iteration_dir(iteration_dir: Path) -> Path:
    root = REPO_ROOT / "iterations"
    candidate = iteration_dir if iteration_dir.is_absolute() else REPO_ROOT / iteration_dir
    if "\x00" in str(candidate) or "\\" in str(candidate):
        raise WriterError("iteration path must not contain NUL")
    try:
        current = Path(root.anchor)
        for part in root.parts:
            current /= part
            if current.is_symlink():
                raise WriterError("iteration path must not pass through a symlink")
        relative = candidate.relative_to(root)
        if ".." in relative.parts:
            raise ValueError("iteration path contains traversal")
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise WriterError("iteration path must not pass through a symlink")
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise WriterError(
            "finalize iteration must be confined to the repository iterations directory"
        ) from exc
    if not resolved.is_dir():
        raise WriterError("finalize iteration directory is missing")
    return resolved


def _current_branch() -> str:
    try:
        return subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterError("无法确认当前 Git 分支，拒绝写入 merged 终态") from exc


def finalize(iteration_dir: Path, merge_sha: str, pr_number: int) -> None:
    iteration_dir = _confined_iteration_dir(iteration_dir)
    if not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha):
        raise WriterError("merge SHA 必须是 40 位小写十六进制")
    if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
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
    if _current_branch() != _RELEASE_BRANCH:
        raise WriterError(f"只能在 {_RELEASE_BRANCH} 分支写入 merged 终态")
    evidence = verify_github_merge(merge_sha, pr_number)
    verification = _make_merge_verification(merge_sha, pr_number, evidence)
    record_merged_event(iteration_dir, verification)


def commit_finalization(iteration_dir: Path) -> None:
    iteration_dir = _confined_iteration_dir(iteration_dir)
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
