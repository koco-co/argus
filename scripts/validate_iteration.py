#!/usr/bin/env python
"""Iteration state machine + staleness validator — STUB (Roadmap 0.3).

Branch-aware transition legality, staleness/reopen verdicts, approval/event
completeness and run-summary invariants are authored in Roadmap 1.3, which
also wires this hook into enforcement. Until then the pre-commit hook
no-ops so the Phase 0 skeleton stays green.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("validate_iteration.py: stub — implemented in Roadmap 1.3", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
