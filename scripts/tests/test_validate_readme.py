"""README 严格校验器的回归测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import _load_script


def test_repository_readmes_pass_strict_validation() -> None:
    validator: Any = _load_script("validate_readme")
    assert validator.main(["--strict"]) == 0


def test_strict_validation_reports_missing_and_escaping_links(tmp_path: Path) -> None:
    validator: Any = _load_script("validate_readme")
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Example\n\n[missing](missing.md)\n[escape](../outside.md)\n", encoding="utf-8"
    )

    errors = validator.validate_readme(readme, root=tmp_path, strict=True)

    assert any("does not exist" in error for error in errors)
    assert any("escapes repository root" in error for error in errors)
