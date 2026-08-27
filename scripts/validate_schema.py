#!/usr/bin/env python
"""Registry-driven artifact schema validator — STUB (Roadmap 0.3).

The shared registry itself exists (``scripts/schema_registry.yaml``; consumed
by ``new_iteration.validate_artifact``). This CLI — registered-fixture exit 0,
unregistered-path/wrong-schema refusal naming the exact JSON path, explicit
FormatChecker — lands with Roadmap 1.2. Until then the pre-commit hook
no-ops so the Phase 0 skeleton stays green.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("validate_schema.py: stub — implemented in Roadmap 1.2", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
