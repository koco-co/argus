"""Roadmap 1.10 acceptance tests for scripts/check_pom_boundary.py.

DoD: four-way fixture matrix (clean/dirty per direction) - locator API inside
tests fails, assert/expect inside page objects fails, both clean forms pass;
covers page.click(".sel") / fill("#id", ...) selector-literal forms, xpath
literals, and the literal-return stub heuristic with its
`# static-copy-ok: <reason>` escape hatch.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_pom_boundary")


def _write(tmp_path: Path, rel: str, body: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _problems(checker: Any, path: Path) -> list[str]:
    report = checker.Report()
    checker.scan_file(path, report)
    return report.problems


# ---------------------------------------------- direction 1: tests clean/dirty


def test_clean_test_file_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_clean.py",
        """\
        def test_checkout(page, checkout_page):
            checkout_page.apply_discount_code("QA")
            total = checkout_page.get_total()
            assert total != ""
        """,
    )
    assert _problems(checker, path) == []


def test_locator_call_in_tests_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_dirty.py",
        """\
        def test_checkout(page):
            page.get_by_role("button", name="Apply").click()
        """,
    )
    problems = _problems(checker, path)
    assert any("get_by_role" in p and "inside tests/" in p for p in problems)


def test_selector_literal_action_form_in_tests_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_forms.py",
        """\
        def test_forms(page):
            page.click(".apply-btn")
            page.fill("#discount", "QA")
            page.check("input[name=terms]")
        """,
    )
    problems = _problems(checker, path)
    assert any("click" in p and ".apply-btn" in p for p in problems)
    assert any("fill" in p and "#discount" in p for p in problems)
    assert any("check" in p for p in problems)


def test_xpath_literal_in_tests_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_xpath.py",
        """\
        def test_xpath(page):
            page.wait_for_selector("//div[@id='modal']")
        """,
    )
    problems = _problems(checker, path)
    assert any("xpath selector literal" in p for p in problems)


# ------------------------------------------ direction 2: page objects clean/dirty


def test_clean_page_object_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/checkout_page.py",
        """\
        class CheckoutPage:
            def __init__(self, page):
                self._page = page

            def _discount_input(self):
                return self._page.get_by_label("Discount code")

            def apply_discount_code(self, code):
                self._discount_input().fill(code)
                self._page.get_by_role("button", name="Apply").click()
                return self

            def get_total(self):
                return self._page.get_by_role("status").inner_text()
        """,
    )
    assert _problems(checker, path) == []


def test_assert_inside_page_object_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/bad_page.py",
        """\
        class BadPage:
            def apply(self, code):
                assert code != ""
                return self
        """,
    )
    problems = _problems(checker, path)
    assert any("assert inside page-object code" in p for p in problems)


def test_expect_inside_component_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/components/navbar/navbar.py",
        """\
        from playwright.sync_api import expect

        class Navbar:
            def is_visible(self):
                expect(self._root).to_be_visible()
                return True
        """,
    )
    problems = _problems(checker, path)
    assert any("expect(...) inside page-object code" in p for p in problems)


# --------------------------------------------------- literal-return heuristic


def test_literal_return_method_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/stub_page.py",
        """\
        class StubPage:
            def get_total(self):
                return "150.00 USD"

            def get_discount_percent(self):
                return 10
        """,
    )
    problems = _problems(checker, path)
    assert any("get_total" in p and "stub-return" in p for p in problems)
    assert any("get_discount_percent" in p and "stub-return" in p for p in problems)


def test_fstring_return_without_interaction_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/fstring_page.py",
        """\
        class FStringPage:
            def describe(self, code):
                return f"discount {code}"
        """,
    )
    problems = _problems(checker, path)
    assert any("stub-return" in p for p in problems)


def test_static_copy_ok_escape_hatch(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/static_page.py",
        """\
        class StaticPage:
            def page_title(self):  # static-copy-ok: title is a fixed site constant
                return "Argus Store"
        """,
    )
    assert _problems(checker, path) == []


# -------------------------------------------------------------- misc: ignored


def test_non_automation_path_is_ignored(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "scripts/whatever.py",
        """\
        page.get_by_role("button").click()
        assert True
        """,
    )
    assert _problems(checker, path) == []
