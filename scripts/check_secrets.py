#!/usr/bin/env python
"""Credential-pattern scan over trackable text — STUB (Roadmap 0.3).

Seeded patterns (Bearer/JWT/AKIA-style/DSN-password) over committed text
including ``00-raw`` dumps are authored in Roadmap 1.13. Until then the
pre-commit hook no-ops so the Phase 0 skeleton stays green.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("check_secrets.py: stub — implemented in Roadmap 1.13", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
