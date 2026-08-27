"""Roadmap 1.11 acceptance tests for scripts/check_test_markers.py.

DoD: missing-marker and mismatched-module fixtures fail; correct sample
passes. Also covers filename/marker agreement and the pytestmark list form.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_test_markers")


GOOD_BODY = """\
    import pytest

    @pytest.mark.module("checkout")
    @pytest.mark.case_id("C0012")
    @pytest.mark.iteration("2026-08-checkout-flow")
    def test_discount():
        assert True
"""


def _write(tmp_path: Path, rel: str, body: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _problems(checker: Any, path: Path) -> list[str]:
    report = checker.Report()
    checker.check_file(path, report)
    return report.problems


def test_correct_sample_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        GOOD_BODY,
    )
    assert _problems(checker, path) == []


def test_missing_marker_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        """\
        import pytest

        @pytest.mark.module("checkout")
        @pytest.mark.iteration("2026-08-checkout-flow")
        def test_discount():
            assert True
        """,
    )
    problems = _problems(checker, path)
    assert any("case_id" in p and "missing required marker" in p for p in problems)


def test_mismatched_module_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        """\
        import pytest

        @pytest.mark.module("auth")
        @pytest.mark.case_id("C0012")
        @pytest.mark.iteration("2026-08-checkout-flow")
        def test_discount():
            assert True
        """,
    )
    problems = _problems(checker, path)
    assert any("does not match the file's module directory 'checkout'" in p for p in problems)


def test_mismatched_iteration_marker_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        """\
        import pytest

        @pytest.mark.module("checkout")
        @pytest.mark.case_id("C0012")
        @pytest.mark.iteration("2025-01-other")
        def test_discount():
            assert True
        """,
    )
    problems = _problems(checker, path)
    assert any("iteration marker '2025-01-other' does not match" in p for p in problems)


def test_mismatched_case_marker_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        """\
        import pytest

        @pytest.mark.module("checkout")
        @pytest.mark.case_id("C9999")
        @pytest.mark.iteration("2026-08-checkout-flow")
        def test_discount():
            assert True
        """,
    )
    problems = _problems(checker, path)
    assert any(
        "case_id marker 'C9999' does not match filename segment 'c0012'" in p for p in problems
    )


def test_pytestmark_list_form_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/api/tests/orders/test_2026-08-orders-api_a0007_fetch_order.py",
        """\
        import pytest

        pytestmark = [
            pytest.mark.module("orders"),
            pytest.mark.case_id("A0007"),
            pytest.mark.iteration("2026-08-orders-api"),
        ]

        def test_fetch():
            assert True
        """,
    )
    assert _problems(checker, path) == []


def test_bare_marker_without_argument_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_2026-08-checkout-flow_c0012_guest_checkout.py",
        """\
        import pytest

        @pytest.mark.module
        @pytest.mark.case_id("C0012")
        @pytest.mark.iteration("2026-08-checkout-flow")
        def test_discount():
            assert True
        """,
    )
    problems = _problems(checker, path)
    assert any("module" in p and "string argument" in p for p in problems)
