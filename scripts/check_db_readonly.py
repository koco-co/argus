#!/usr/bin/env python
"""DB read-only static scans (Roadmap 1.9 / ARCHITECTURE §6 Layer 3).

Two AST-based behaviors, dispatched by path:

1. Write-verb scan (files under ``shared/db/**``): write verbs appearing as
   executable code identifiers (function names, calls, attributes) are
   checked against the unified denylist - INSERT UPDATE DELETE MERGE REPLACE
   UPSERT CALL EXEC COPY GRANT ALTER DROP TRUNCATE CREATE - implemented over
   AST tokens so string and comment literals never trip it. The only escape
   hatch is a reviewed line comment ``# db-write-ok: <reason>`` (reserved for
   the checker's own unit tests).

2. Raw DB-driver import scan (every other Python path passed in, e.g.
   ``automation/**`` and ``shared/assertions/**``): direct imports of DB
   drivers (psycopg, psycopg2, pymysql, sqlite3, ...) fail - every query must
   flow through ``shared/db/readonly_client.py``, the sole sanctioned access
   path. Imports under ``shared/db/**`` are the sanctioned exception.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

_WRITE_VERBS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "REPLACE",
    "UPSERT",
    "CALL",
    "EXEC",
    "COPY",
    "GRANT",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "CREATE",
}
_ESCAPE = re.compile(r"#\s*db-write-ok:\s*(?P<reason>.+)")
_DB_DRIVERS = {
    "psycopg",
    "psycopg2",
    "psycopg_binary",
    "pymysql",
    "mysqldb",
    "sqlite3",
    "sqlalchemy",
    "asyncpg",
    "pg8000",
    "pyodbc",
    "cx_Oracle",
    "cassandra",
    "pymongo",
    "redis",
    "elasticsearch",
}
_SHARED_DB = "shared/db/"


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def _identifier_tokens(identifier: str) -> set[str]:
    """Split an identifier into lowercase word tokens: delete_user -> {delete, user}."""
    return {token for token in re.split(r"[^a-zA-Z0-9]+", identifier.lower()) if token}


def _line_has_escape(source_lines: list[str], lineno: int) -> bool:
    line = source_lines[lineno - 1] if 0 < lineno <= len(source_lines) else ""
    match = _ESCAPE.search(line)
    return bool(match and match.group("reason").strip())


def scan_write_verbs(path: Path, source: str, report: Report) -> None:
    import ast

    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    flagged: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        candidates: list[tuple[int, str]] = []
        if isinstance(node, ast.Name):
            candidates = [(node.lineno, node.id)]
        elif isinstance(node, ast.Attribute):
            candidates = [(node.lineno, node.attr)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            candidates = [(node.lineno, node.name)]
        for lineno, identifier in candidates:
            verbs = _identifier_tokens(identifier) & {v.lower() for v in _WRITE_VERBS}
            if verbs and (lineno, identifier) not in flagged:
                if _line_has_escape(source_lines, lineno):
                    continue
                for verb in sorted(verbs):
                    report.fail(
                        f"{path}:{lineno}: write verb '{verb.upper()}' in executable "
                        f"identifier {identifier!r} (escape only via # db-write-ok: <reason>)"
                    )
                flagged.add((lineno, identifier))


def scan_driver_imports(path: Path, source: str, report: Report) -> None:
    import ast

    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".")[0]]
        for name in names:
            if name.lower() in _DB_DRIVERS:
                lineno = getattr(node, "lineno", 0)
                report.fail(
                    f"{path}:{lineno}: raw DB-driver import {name!r} - every query "
                    f"must flow through shared/db/readonly_client.py"
                )


def scan_file(path: Path, report: Report) -> None:
    source = path.read_text(encoding="utf-8")
    relative = path.as_posix()
    if relative.startswith(_SHARED_DB) or f"/{_SHARED_DB}" in f"/{relative}":
        scan_write_verbs(path, source, report)
    else:
        scan_driver_imports(path, source, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="Python files to scan")
    parser.add_argument(
        "--all",
        action="store_true",
        help="scan shared/db plus automation and shared/assertions trees",
    )
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        for directory in ("shared/db", "shared/assertions", "automation"):
            targets.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    for path in targets:
        if path.is_file():
            scan_file(path, report)

    for problem in report.problems:
        print(f"db-readonly violation: {problem}")
    if report.problems:
        print(f"check_db_readonly: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_db_readonly: {len(targets)} file(s) clean")
    return 0
