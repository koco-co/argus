"""Roadmap 1.15 acceptance tests for scripts/check_patch_scope.py.

DoD fixtures: clean, frozen-path, assertion-change, expected-fixture-change,
banned-pattern and outside-allow-list patches hard-fail/pass exactly as the
verification battery requires.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_patch_scope")


def _problems(checker: Any, patch: str) -> list[str]:
    report = checker.Report()
    checker.check_patch_text(patch, report)
    return report.problems


CLEAN_LOCATOR_PATCH = """\
--- a/automation/web/pages/checkout/checkout_page.py
+++ b/automation/web/pages/checkout/checkout_page.py
@@ -3,5 +3,5 @@
     def _apply_button(self):
-        return self._page.get_by_label("Apply")
+        return self._page.get_by_role("button", name="Apply")
"""


def test_clean_locator_patch_passes(checker: Any) -> None:
    assert _problems(checker, CLEAN_LOCATOR_PATCH) == []


def test_frozen_test_path_fails(checker: Any) -> None:
    patch = CLEAN_LOCATOR_PATCH.replace(
        "+++ b/automation/web/pages/checkout/checkout_page.py",
        "+++ b/automation/web/tests/checkout/test_discount.py",
    ).replace(
        "--- a/automation/web/pages/checkout/checkout_page.py",
        "--- a/automation/web/tests/checkout/test_discount.py",
    )
    problems = _problems(checker, patch)
    assert any("outside allow-list" in p for p in problems)


def test_assertion_change_fails(checker: Any) -> None:
    patch = """\
--- a/automation/web/tests/checkout/test_discount.py
+++ b/automation/web/tests/checkout/test_discount.py
@@ -1,4 +1,4 @@
-    assert total == "150.00"
+    assert total != ""
"""
    problems = _problems(checker, patch)
    assert any("outside allow-list" in p for p in problems)
    assert any("tests/checkout" in p for p in problems)


def test_expected_fixture_change_fails(checker: Any) -> None:
    patch = """\
--- a/shared/testdata/seed_checkout.py
+++ b/shared/testdata/seed_checkout.py
@@ -1,4 +1,4 @@
-EXPECTED_DISCOUNT_TOTAL = "150.00"
+EXPECTED_DISCOUNT_TOTAL = "120.00"
"""
    problems = _problems(checker, patch)
    assert any("frozen shared-testdata content" in p for p in problems)
    assert any("expected" in p.lower() for p in problems)


def test_seed_formula_change_fails(checker: Any) -> None:
    patch = """\
--- a/shared/testdata/seed_checkout.py
+++ b/shared/testdata/seed_checkout.py
@@ -1,4 +1,4 @@
-def seed_discount_total(base):
+def seed_discount_total(base, vat):
     return base * 0.9
"""
    problems = _problems(checker, patch)
    assert any("frozen shared-testdata" in p for p in problems)


def test_banned_skip_pattern_in_allowed_path_fails(checker: Any) -> None:
    patch = """\
--- a/automation/web/pages/checkout/checkout_page.py
+++ b/automation/web/pages/checkout/checkout_page.py
@@ -1,4 +1,5 @@
+    pytest.skip("unstable today")
     def apply(self, code):
         return self
"""
    problems = _problems(checker, patch)
    assert any("banned pattern 'pytest.skip/xfail'" in p for p in problems)


def test_assert_true_banned_pattern_fails(checker: Any) -> None:
    patch = """\
--- a/automation/api/clients/orders/orders_client.py
+++ b/automation/api/clients/orders/orders_client.py
@@ -1,4 +1,5 @@
+    assert True
     def get_order(self, order_id: str) -> OrderResponse:
         return OrderResponse.model_validate({})
"""
    problems = _problems(checker, patch)
    assert any("banned pattern 'assert True'" in p for p in problems)


def test_outside_allow_list_config_change_fails(checker: Any) -> None:
    patch = """\
--- a/config/env.example.yaml
+++ b/config/env.example.yaml
@@ -1,3 +1,4 @@
+base_url: "http://localhost"
"""
    problems = _problems(checker, patch)
    assert any("outside allow-list" in p and "config/env.example.yaml" in p for p in problems)


def test_testdata_reseed_wiring_without_frozen_content_passes(checker: Any) -> None:
    """data_issue repair may adjust reseed-hook wiring / namespace arguments."""
    patch = """\
--- a/shared/testdata/hooks.py
+++ b/shared/testdata/hooks.py
@@ -1,4 +1,4 @@
-def reseed(run_id):
+def reseed(run_id, namespace):
     return f"{run_id}-{namespace}"
"""
    assert _problems(checker, patch) == []
