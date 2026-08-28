#!/usr/bin/env python
"""Sole writer of iteration ``state`` transitions and ``events[]``
(Roadmap 1.15b, PRD §6). Usage:

    record_event.py iterations/<id> --from <state> --to <state> \
        --by {agent,script,user} [--reason "..."]

Refuses stale/illegal transitions and hand-edited files; see
scripts/_writers.py for the shared sole-writer core.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _writers import ACTORS, WriterError, record_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    parser.add_argument("--from", dest="from_state", required=True)
    parser.add_argument("--to", dest="to_state", required=True)
    parser.add_argument("--by", choices=ACTORS, required=True)
    parser.add_argument("--reason", help="required when --to blocked")
    parser.add_argument("--merge-sha", help="仅 accepted -> merged 使用")
    parser.add_argument("--pr-number", type=int, help="仅 accepted -> merged 使用")
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
        )
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"record_event: state -> {document['state']} (by {args.by})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
