#!/usr/bin/env python
"""发送执行摘要或 CI job 状态；渠道失败不改变原测试终态。"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

import yaml

# 规范命令以脚本路径执行；此时 Python 只把 scripts/ 放入 sys.path。
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_dispatcher = importlib.import_module("shared.notify.dispatcher")
build_notifiers = _dispatcher.build_notifiers
dispatch = _dispatcher.dispatch
load_config = _dispatcher.load_config
newest_summary = _dispatcher.newest_summary
render_summary = _dispatcher.render_summary


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
    config = load_config(args.config)
    if args.summary:
        path = (
            newest_summary(REPO_ROOT / "iterations")
            if args.summary == "auto"
            else Path(args.summary)
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        message = render_summary(document, args.classification)
    else:
        message = f"Argus CI job\n任务: {args.job}\n状态: {args.classification or args.status}"
    results = dispatch(message, build_notifiers(config))
    failed = [name for name, passed in results.items() if not passed]
    print(f"notify: 成功 {sum(results.values())}，失败 {len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
