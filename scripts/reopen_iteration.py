#!/usr/bin/env python
"""用户或受托代理重开迭代并传播 stale（Roadmap 1.15b、PRD §5）。

用法：``reopen_iteration.py iterations/<id> [--reason "..."]``。

用户可直接重开；agent 必须绑定 iteration.delegation 中的结构化授权，
将迭代退回 ``requirements_clarifying``。所有已分配 ID 保持不变，下游产物
标记为 ``stale``，直到重新生成或明确重新确认；重开后的正常推进仍只能使用
各自的唯一写入器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _writers import WriterError, load_iteration, record_event


def reopen(
    iteration_dir: Path, reason: str | None, triggered_by: str, delegation_id: str | None
) -> dict:
    _, document = load_iteration(iteration_dir)
    # stale 传播与 reopen 事件由唯一事件写入器一次落盘，拒绝时文件字节不变。
    return record_event(
        iteration_dir,
        from_state=document["state"],
        to_state="requirements_clarifying",
        triggered_by=triggered_by,
        reason=reason,
        mark_downstream_stale=True,
        delegation_id=delegation_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> 目录")
    parser.add_argument("--reason", help="重开迭代的原因")
    parser.add_argument("--by", choices=("user", "agent"), default="user")
    parser.add_argument("--delegation-id", help="agent reopen 必须引用的授权 ID")
    args = parser.parse_args(argv)

    try:
        document = reopen(args.iteration, args.reason, args.by, args.delegation_id)
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    stale_keys = sorted(
        key for key, entry in document["artifacts"].items() if entry.get("status") == "stale"
    )
    print(f"reopen_iteration: {document['iteration_id']} -> requirements_clarifying")
    print(f"reopen_iteration: IDs preserved; stale artifacts: {', '.join(stale_keys) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
