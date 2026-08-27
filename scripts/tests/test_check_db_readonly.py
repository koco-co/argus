"""Roadmap 1.9 acceptance tests for scripts/check_db_readonly.py.

DoD: pass/fail fixtures per behavior (write-verb identifiers caught, string
literals never trip the scan, escape hatch honored, driver imports caught,
sanctioned shared/db imports pass).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_db_readonly")


def _report(checker: Any, path: Path) -> list[str]:
    report = checker.Report()
    checker.scan_file(path, report)
    return report.problems


def _db_file(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "shared" / "db" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_select_only_wrapper_code_passes(checker: Any, tmp_path: Path) -> None:
    path = _db_file(
        tmp_path,
        "readonly_client.py",
        """\
        class ReadOnlyDBClient:
            def query(self, sql, params=()):
                head = sql.split(None, 1)[0].lower()
                return self._conn.execute(sql, params).fetchall()
        """,
    )
    assert _report(checker, path) == []


def test_write_verb_identifier_fails(checker: Any, tmp_path: Path) -> None:
    path = _db_file(
        tmp_path,
        "writer.py",
        """\
        def insert_row(row):
            return row

        def delete_old_rows():
            insert_row(None)
        """,
    )
    problems = _report(checker, path)
    assert any("INSERT" in p and "insert_row" in p for p in problems)
    assert any("DELETE" in p and "delete_old_rows" in p for p in problems)


def test_string_literals_never_trip_the_scan(checker: Any, tmp_path: Path) -> None:
    path = _db_file(
        tmp_path,
        "reads.py",
        """\
        def counts(conn):
            return conn.execute("SELECT count(*) FROM t").fetchall()

        QUERY = "DROP TABLE statements are strings, not code identifiers"
        """,
    )
    assert _report(checker, path) == []


def test_escape_hatch_requires_reason(checker: Any, tmp_path: Path) -> None:
    path = _db_file(
        tmp_path,
        "migrate_stub.py",
        """\
        def create_schema(conn):  # db-write-ok: checker unit test
            conn.execute("CREATE TABLE t (id int)")
        """,
    )
    assert _report(checker, path) == []

    path_no_reason = _db_file(
        tmp_path,
        "no_reason.py",
        """\
        def create_schema(conn):  # db-write-ok
            conn.execute("CREATE TABLE t (id int)")
        """,
    )
    problems = _report(checker, path_no_reason)
    assert any("CREATE" in p for p in problems)


def test_driver_import_outside_shared_db_fails(checker: Any, tmp_path: Path) -> None:
    path = tmp_path / "automation" / "web" / "tests" / "checkout" / "test_bad.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import psycopg\n\ndef test_x():\n    assert True\n", encoding="utf-8")
    problems = _report(checker, path)
    assert any("raw DB-driver import 'psycopg'" in p for p in problems)


def test_driver_from_import_caught(checker: Any, tmp_path: Path) -> None:
    path = tmp_path / "shared" / "assertions" / "db_asserts.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from psycopg2 import connect\n", encoding="utf-8")
    problems = _report(checker, path)
    assert any("'psycopg2'" in p for p in problems)


def test_sanctioned_driver_import_in_shared_db_passes(checker: Any, tmp_path: Path) -> None:
    path = _db_file(tmp_path, "readonly_client.py", "import psycopg\n")
    assert _report(checker, path) == []
