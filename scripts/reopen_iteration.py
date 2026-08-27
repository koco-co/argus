#!/usr/bin/env python
"""User-triggered reopen + stale propagation (Roadmap 1.15b, PRD §5).

    reopen_iteration.py iterations/<id> [--reason "..."]

Records a user reopen event back to ``requirements_clarifying``, preserves
every allocated ID (no artifact file is touched or renumbered) and marks all
downstream artifacts ``stale`` so stale consumers are blocked until
regeneration or explicit re-confirmation. Leaving the reopened state
continues through the normal sole writers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _writers import WriterError, load_iteration, propagate_stale, record_event


def reopen(iteration_dir: Path, reason: str | None) -> dict:
    iteration_yaml, document = load_iteration(iteration_dir)
    propagate_stale(document)
    # persist the stale statuses first (part of the reopen event's meaning),
    # then record the user event through the sole transition writer.
    iteration_yaml.write_text(yaml_safe_dump(document), encoding="utf-8")
    document = record_event(
        iteration_dir,
        from_state=document["state"],
        to_state="requirements_clarifying",
        triggered_by="user",
        reason=reason,
    )
    return document


def yaml_safe_dump(document: dict) -> str:
    import yaml

    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    parser.add_argument("--reason", help="why the iteration is reopened")
    args = parser.parse_args(argv)

    try:
        document = reopen(args.iteration, args.reason)
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
