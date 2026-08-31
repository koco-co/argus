#!/usr/bin/env python
"""迭代 ``approvals[]`` 的唯一写入器（Roadmap 1.15b、PRD §6）。

用法：

    record_approval.py iterations/<id> --stage <stage> --action <action> \
        --artifact <file-to-hash> [--note "..."]

显式用户决定记录 ``actor: user``。结构化持续授权下的代理决定记录
``action: delegated, actor: agent``，并且必须带非空审查说明。每条记录都绑定产物
摘要；``stage=environment`` 使用环境文件的脱敏副本（保留键和结构、遮蔽值）计算摘要，
避免批准记录成为针对低熵密钥的暴力枚举预言机。共享实现见 ``scripts/_writers.py``。
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from _writers import (
    APPROVAL_ACTIONS,
    APPROVAL_STAGES,
    WriterError,
    artifact_digest,
    record_approval,
    redacted_digest,
)

# AGENTS.md 规定直接执行本脚本；显式加入仓库根目录才能导入 shared/。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
check_path = importlib.import_module("shared.config.settings").check_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> 目录")
    parser.add_argument("--stage", choices=APPROVAL_STAGES, required=True)
    parser.add_argument("--action", choices=APPROVAL_ACTIONS, required=True)
    parser.add_argument("--artifact", type=Path, help="需要记录摘要的产物文件")
    parser.add_argument("--sha256", help="预先计算的产物摘要（64 位十六进制）")
    parser.add_argument(
        "--note",
        help="审查说明；代理决定和环境参数批准必须提供",
    )
    parser.add_argument(
        "--delegation-id",
        help="delegated 决定引用的 iteration.yaml delegation.id",
    )
    args = parser.parse_args(argv)

    if args.stage == "environment":
        if args.artifact is None:
            print(
                "error: environment approval requires --artifact so settings.py check can run",
                file=sys.stderr,
            )
            return 1
        problems = check_path(args.artifact, args.iteration)
        if problems:
            for problem in problems:
                print(f"error: environment check failed: {problem}", file=sys.stderr)
            return 1

    try:
        if args.artifact is not None:
            digest = (
                redacted_digest(args.artifact)
                if args.stage == "environment"
                else artifact_digest(args.artifact)
            )
        elif args.sha256:
            digest = args.sha256
        else:
            parser.error("pass --artifact <file> or --sha256 <hex>")
            return 2
        document = record_approval(
            args.iteration,
            args.stage,
            args.action,
            digest,
            args.note,
            args.delegation_id,
        )
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"record_approval: {args.stage}/{args.action} "
        f"by {'agent' if args.action == 'delegated' else 'user'} "
        f"(approvals total: {len(document['approvals'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
