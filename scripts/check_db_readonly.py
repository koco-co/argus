#!/usr/bin/env python
"""DB write-verb scan — STUB (Roadmap 0.3).

The AST token scan over ``shared/db/**`` (unified denylist incl.
MERGE/REPLACE/UPSERT/CALL/EXEC/COPY, ``# db-write-ok`` escape hatch) plus the
CI driver-import scan are authored in Roadmap 1.9. Until then the pre-commit
hook no-ops so the Phase 0 skeleton stays green.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("check_db_readonly.py: stub — implemented in Roadmap 1.9", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
