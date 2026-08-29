"""Roadmap 5.3：故障证据的机械预分类。"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def classifier() -> Any:
    return _load_script("classify_failure")


@pytest.mark.parametrize(
    ("evidence", "expected", "escalation"),
    [
        ({"error_type": "TimeoutError", "element_present": False}, "locator_drift", False),
        (
            {"error_type": "AssertionError", "element_present": True, "actual_differs": True},
            "product_behavior_mismatch",
            True,
        ),
        ({"status_code": 503}, "backend_5xx", True),
        ({"status_code": 401}, "auth_failure", True),
        ({"redirected_to_login": True}, "auth_failure", True),
        ({"connection_error": True}, "environment_unavailable", True),
        ({"error_type": "FixtureLookupError"}, "fixture_error", False),
        ({"error_type": "ValidationError"}, "serialization_error", False),
        ({"error_type": "ImportError"}, "import_type_error", False),
        ({"requirement_conflict": True}, "requirement_conflict", True),
    ],
)
def test_classification_branches(
    classifier: Any, evidence: dict[str, Any], expected: str, escalation: bool
) -> None:
    verdict = classifier.classify(evidence)
    assert verdict.failure_class == expected
    assert verdict.escalation_only is escalation


def test_escalation_class_cannot_be_refined_to_repairable(classifier: Any) -> None:
    verdict = classifier.classify({"status_code": 500})
    with pytest.raises(ValueError, match="不得降级"):
        classifier.refine(verdict, "timing")
