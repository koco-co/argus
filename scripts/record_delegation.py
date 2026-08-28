#!/usr/bin/env python
"""记录当前任务的用户持续授权范围（唯一 delegation writer）。

delegated approval 只能引用 iteration.yaml 中这条结构化授权；授权的 basis
及摘要、范围和有效期都会被 Schema 与生命周期校验器复核。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _writers import DELEGATION_SCOPES, WriterError, record_delegation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> 目录")
    parser.add_argument("--id", dest="delegation_id", required=True)
    parser.add_argument("--basis", required=True, help="用户持续授权的明确依据")
    parser.add_argument(
        "--scope",
        action="append",
        choices=DELEGATION_SCOPES,
        required=True,
        help="授权可以覆盖的阶段；可重复传入",
    )
    parser.add_argument("--granted-at", required=True)
    parser.add_argument("--expires-at", required=True)
    args = parser.parse_args(argv)
    try:
        document = record_delegation(
            args.iteration,
            args.delegation_id,
            args.basis,
            args.scope,
            args.granted_at,
            args.expires_at,
        )
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"record_delegation: {document['delegation']['id']} 已记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
