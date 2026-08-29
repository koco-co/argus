#!/usr/bin/env python
"""迭代 ``state`` 与 ``events[]`` 的唯一写入器（Roadmap 1.15b、PRD §6）。

用法：

    record_event.py iterations/<id> --from <state> --to <state> \
        --by {agent,script,user} [--reason "..."] [--delegation-id <id>]

脚本会拒绝过期或非法状态迁移及手工改写的文件；共享的唯一写入逻辑见
``scripts/_writers.py``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _writers import ACTORS, WriterError, record_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> 目录")
    parser.add_argument("--from", dest="from_state", required=True)
    parser.add_argument("--to", dest="to_state", required=True)
    parser.add_argument("--by", choices=ACTORS, required=True)
    parser.add_argument("--reason", help="目标为 blocked 时必填")
    parser.add_argument("--merge-sha", help="仅 accepted -> merged 使用")
    parser.add_argument("--pr-number", type=int, help="仅 accepted -> merged 使用")
    parser.add_argument("--delegation-id", help="delegated reopen 使用的授权 ID")
    args = parser.parse_args(argv)

    try:
        document = record_event(
            args.iteration,
            args.from_state,
            args.to_state,
            args.by,
            args.reason,
            args.merge_sha,
            args.pr_number,
            delegation_id=args.delegation_id,
        )
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"record_event: state -> {document['state']} (by {args.by})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
