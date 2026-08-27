#!/usr/bin/env python
"""Sole writer of iteration ``approvals[]`` (Roadmap 1.15b, PRD §6).
Usage:

    record_approval.py iterations/<id> --stage <stage> --action <action> \
        --artifact <file-to-hash> [--note "..."]

Every approval records ``actor: user`` and the artifact digest. For
``stage=environment`` the digest is computed over a REDACTED copy of the env
file (values masked, keys preserved) so approvals never double as brute-force
oracles against low-entropy secrets. See scripts/_writers.py.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    parser.add_argument("--stage", choices=APPROVAL_STAGES, required=True)
    parser.add_argument("--action", choices=APPROVAL_ACTIONS, required=True)
    parser.add_argument("--artifact", type=Path, help="file whose digest is recorded")
    parser.add_argument("--sha256", help="pre-computed artifact digest (64 hex)")
    parser.add_argument("--note", help="human context, e.g. the approved parameter set")
    args = parser.parse_args(argv)

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

    try:
        document = record_approval(args.iteration, args.stage, args.action, digest, args.note)
    except WriterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"record_approval: {args.stage}/{args.action} by user "
        f"(approvals total: {len(document['approvals'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
