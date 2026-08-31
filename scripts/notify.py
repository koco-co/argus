#!/usr/bin/env python
"""发送执行摘要或 CI job 状态；渠道失败不改变原测试终态。"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

# 规范命令以脚本路径执行；此时 Python 只把 scripts/ 放入 sys.path。
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_yaml = importlib.import_module("argus_core.parsing").load_yaml

_dispatcher = importlib.import_module("shared.notify.dispatcher")
build_notifiers = _dispatcher.build_notifiers
dispatch = _dispatcher.dispatch
load_config = _dispatcher.load_config
newest_summary = _dispatcher.newest_summary
render_summary = _dispatcher.render_summary


def _safe_summary_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if "\x00" in str(candidate) or "\\" in str(candidate):
        raise ValueError("summary path contains NUL or backslash")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("summary 必须是项目目录内的普通文件")
    try:
        root = REPO_ROOT.resolve()
        relative = candidate.relative_to(root)
        if ".." in relative.parts:
            raise ValueError("summary path contains traversal")
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("summary path must not pass through a symlink")
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError("summary 必须位于项目目录内") from exc
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--summary", help="run-summary.yaml 路径，或 auto")
    parser.add_argument("--job", help="无 run 摘要时发送 CI job 名")
    parser.add_argument("--status", default="unknown")
    parser.add_argument("--classification")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config/notify.yaml")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.summary and not args.job:
        parser.error("必须传 --summary 或 --job")
    if args.job and not (args.classification or args.status).strip():
        parser.error("--job 模式的 --status 不得为空")
    try:
        config = load_config(args.config)
        if args.summary:
            path = (
                newest_summary(REPO_ROOT / "iterations")
                if args.summary == "auto"
                else _safe_summary_path(args.summary)
            )
            document = load_yaml(path.read_bytes()) or {}
            if not isinstance(document, dict):
                raise ValueError("summary 顶层必须是映射")
            message = render_summary(document, args.classification)
        else:
            message = f"Argus CI job\n任务: {args.job}\n状态: {args.status}"
            if args.classification:
                message += f"\n分类: {args.classification}"
    except (OSError, ValueError) as exc:
        print(f"error: 无法读取通知输入：{exc}", file=sys.stderr)
        return 1
    results = dispatch(message, build_notifiers(config))
    failed = [name for name, passed in results.items() if not passed]
    print(f"notify: 成功 {sum(results.values())}，失败 {len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
