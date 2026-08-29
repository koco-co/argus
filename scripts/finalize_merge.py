#!/usr/bin/env python
"""在真实合并后记录 release 上的 merged 状态与 GitHub 事实。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from _writers import WriterError, load_iteration, record_event
from check_coverage import main as coverage_main
from validate_iteration import IterationReport, check_iteration

REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[a-f0-9]{40}$")


def finalize(iteration_dir: Path, merge_sha: str, pr_number: int) -> None:
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
    record_event(
        iteration_dir,
        "accepted",
        "merged",
        "script",
        merge_sha=merge_sha,
        pr_number=pr_number,
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
