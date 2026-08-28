"""Roadmap 1.17 acceptance tests for scripts/check_prod_scope.py.

DoD: violating fixture fails naming the offending nodeid and method; clean
read-only suite passes; per-project denylist names honored; escape via
reviewed # prod-ok: <reason>.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_prod_scope")


def _write(tmp_path: Path, rel: str, body: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _problems(checker: Any, path: Path, denylist_file: Path | None = None) -> list[str]:
    report = checker.Report()
    denylist = checker.load_denylist(denylist_file)
    checker.scan_file(path, denylist, report)
    return report.problems


def test_clean_read_only_suite_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_read.py",
        """\
        import pytest

        @pytest.mark.read_only
        @pytest.mark.module("checkout")
        def test_read_only(page, checkout_page):
            total = checkout_page.get_total()
            assert total != ""
        """,
    )
    assert _problems(checker, path) == []


def test_write_shaped_call_fails_naming_nodeid_and_method(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_write.py",
        """\
        import pytest

        @pytest.mark.read_only
        @pytest.mark.module("checkout")
        def test_creates_order(client):
            client.delete_order("42")
        """,
    )
    problems = _problems(checker, path)
    assert any("delete_order" in p for p in problems)
    assert any("test_write.py::test_creates_order" in p for p in problems)


def test_prod_ok_escape_honored(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_escape.py",
        """\
        import pytest

        @pytest.mark.read_only
        def test_wrapped(client):
            client.delete_order("42")  # prod-ok: reviewed read-probe on a scratch row
        """,
    )
    assert _problems(checker, path) == []


def test_unmarked_test_is_not_audited(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_unmarked.py",
        """\
        def test_writer(client):
            client.delete_order("42")
        """,
    )
    assert _problems(checker, path) == []


def test_per_project_denylist_name_honored(checker: Any, tmp_path: Path) -> None:
    denylist = _write(tmp_path, "denylist.yaml", "- purge_cache\n")
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_purge.py",
        """\
        import pytest

        @pytest.mark.read_only
        def test_purges(env):
            env.purge_cache()
        """,
    )
    problems = _problems(checker, path, denylist)
    assert any("purge_cache" in p for p in problems)
