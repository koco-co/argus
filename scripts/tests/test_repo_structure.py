"""Roadmap 0.8 acceptance test: repo skeleton matches ARCHITECTURE §2 exactly.

The doc tree is the single structural authority (ARCHITECTURE §2); this test
is the structural diff. Governed roots may not sprout undeclared children —
new structure enters the docs first, then this expected set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runner/tool noise and sanctioned structural placeholders never count.
IGNORED_NAMES = {
    ".DS_Store",
    ".gitkeep",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".git",
    ".mimosa",
    ".vscode",
}

EXPECTED_DIRS: set[str] = {
    # skills layer: six skills, each with schemas/examples/versions (ADR-007)
    *(
        f".agents/skills/{skill}/{sub}"
        for skill in (
            "functional-test-design",
            "api-test-design",
            "web-automation-generation",
            "api-automation-generation",
            "self-debug-runner",
            "skill-self-optimizer",
        )
        for sub in ("schemas", "examples", "versions")
    ),
    ".claude/skills",
    "plugins/_interface/schemas",
    "plugins/requirement-sources",
    "plugins/api-sources",
    "iterations",
    "target-app",
    "automation/web/pages",
    "automation/web/components",
    "automation/web/fixtures",
    "automation/web/tests",
    "automation/mobile/android",
    "automation/mobile/ios",
    "automation/mobile/screens",
    "automation/mobile/tests",
    "automation/miniprogram/pages",
    "automation/miniprogram/tests",
    "automation/api/clients",
    "automation/api/models",
    "automation/api/tests",
    "automation/api/har",
    "automation/perf/locustfiles",
    "automation/perf/scenarios",
    "shared/utils",
    "shared/assertions",
    "shared/config",
    "shared/db",
    "shared/notify",
    "shared/testdata",
    "reports/allure-results",
    "reports/allure-report",
    "knowledge/target-app-notes",
    "scripts/schemas",
    "scripts/tests",
    "scripts/tests/fixtures",
    ".github/workflows",
    "docs/spec",
}

# Directories whose only tracked content at Phase 0 is a .gitkeep keeper.
KEEPER_DIRS: set[str] = {
    ".claude/skills",
    "plugins/_interface/schemas",
    "plugins/requirement-sources",
    "plugins/api-sources",
    "iterations",
    "target-app",
    "automation/web/pages",
    "automation/web/components",
    "automation/web/fixtures",
    "automation/web/tests",
    "automation/mobile/android",
    "automation/mobile/ios",
    "automation/mobile/screens",
    "automation/mobile/tests",
    "automation/miniprogram/pages",
    "automation/miniprogram/tests",
    "automation/api/clients",
    "automation/api/models",
    "automation/api/tests",
    "automation/api/har",
    "automation/perf/locustfiles",
    "automation/perf/scenarios",
    "shared/utils",
    "shared/assertions",
    "shared/config",
    "shared/db",
    "shared/notify",
    "shared/testdata",
    "reports/allure-results",
    "reports/allure-report",
    "knowledge/target-app-notes",
    ".github/workflows",
}

EXPECTED_FILES: set[str] = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".pre-commit-config.yaml",
    "Makefile",
    ".gitignore",
    "plugins/README.md",
    "plugins/registry.yaml",
    "config/env.example.yaml",
    "config/notify.example.yaml",
    "knowledge/patterns.md",
    "knowledge/anti-patterns.md",
    "knowledge/optimization-candidates.yaml",
    "automation/conftest.py",
    "scripts/new_iteration.py",
    "scripts/_registry_lib.py",
    "scripts/schema_registry.yaml",
    "scripts/schemas/iteration.schema.json",
    "scripts/validate_schema.py",
    "scripts/validate_iteration.py",
    "scripts/check_db_readonly.py",
    "scripts/check_secrets.py",
    *(f"{d}/.gitkeep" for d in KEEPER_DIRS),
}

# root -> declared immediate children (dirs end with '/', files bare).
# Anything else under these roots is a structural defect (ADR-007 drift).
GOVERNED_CHILDREN: dict[str, set[str]] = {
    ".agents/skills": {
        "functional-test-design",
        "api-test-design",
        "web-automation-generation",
        "api-automation-generation",
        "self-debug-runner",
        "skill-self-optimizer",
    },
    "plugins": {"README.md", "registry.yaml", "_interface", "requirement-sources", "api-sources"},
    "plugins/_interface": {"schemas"},
    "config": {"env.example.yaml", "notify.example.yaml"},
    "automation": {"conftest.py", "web", "mobile", "miniprogram", "api", "perf"},
    "automation/web": {"pages", "components", "fixtures", "tests"},
    "automation/mobile": {"android", "ios", "screens", "tests"},
    "automation/miniprogram": {"pages", "tests"},
    "automation/api": {"clients", "models", "tests", "har"},
    "automation/perf": {"locustfiles", "scenarios"},
    "shared": {"utils", "assertions", "config", "db", "notify", "testdata"},
    "reports": {"allure-results", "allure-report"},
    "knowledge": {
        "patterns.md",
        "anti-patterns.md",
        "optimization-candidates.yaml",
        "target-app-notes",
    },
    "scripts": {
        "new_iteration.py",
        "_registry_lib.py",
        "schema_registry.yaml",
        # Roadmap 0.3 stub entries — real logic lands in Phases 1-2
        # (validate_schema.py is real since 1.2).
        "validate_schema.py",
        "validate_iteration.py",
        "check_db_readonly.py",
        "check_secrets.py",
        "check_layering.py",
        "check_pom_boundary.py",
        "check_test_markers.py",
        "check_api_models.py",
        "render_md.py",
        "export_xmind.py",
        "export_xlsx.py",
        "check_coverage.py",
        "check_api_coverage.py",
        "check_patch_scope.py",
        "check_functional_expectations.py",
        "schemas",
        "tests",
    },
    "scripts/tests": {
        "conftest.py",
        "fixtures",
        "test_new_iteration.py",
        "test_repo_structure.py",
        "test_schemas.py",
        "test_docs_schemas.py",
        "test_schema_validator.py",
        "test_validate_iteration.py",
        "test_render_md.py",
        "test_export_xmind.py",
        "test_export_xlsx.py",
        "test_check_coverage.py",
        "test_check_api_coverage.py",
        "test_check_db_readonly.py",
        "test_check_pom_boundary.py",
        "test_check_patch_scope.py",
        "test_check_functional_expectations.py",
        "test_check_test_markers.py",
        "test_check_api_models.py",
        "test_check_secrets.py",
        "test_check_layering.py",
    },
    "target-app": set(),
}


def test_expected_directories_exist() -> None:
    missing = sorted(d for d in EXPECTED_DIRS if not (REPO_ROOT / d).is_dir())
    assert missing == []


def test_expected_files_exist() -> None:
    missing = sorted(f for f in EXPECTED_FILES if not (REPO_ROOT / f).is_file())
    assert missing == []


def test_keeper_dirs_hold_a_gitkeep() -> None:
    empty = sorted(d for d in KEEPER_DIRS if not (REPO_ROOT / d / ".gitkeep").is_file())
    assert empty == []


@pytest.mark.parametrize("root", sorted(GOVERNED_CHILDREN))
def test_governed_roots_have_no_undeclared_children(root: str) -> None:
    root_path = REPO_ROOT / root
    assert root_path.is_dir(), f"governed root {root} missing"
    actual = {p.name for p in root_path.iterdir() if p.name not in IGNORED_NAMES}
    declared = GOVERNED_CHILDREN[root]
    undeclared = sorted(actual - declared)
    assert undeclared == [], f"undeclared entries under {root}: {undeclared}"


def test_automation_module_leaf_dirs_are_empty_beyond_keepers() -> None:
    """Generated modules arrive with the generation skills (Phases 5/6)."""
    leaf_dirs = [
        d
        for d in EXPECTED_DIRS
        if d.startswith(("automation/", "shared/")) and (REPO_ROOT / d).is_dir()
    ]
    polluted = sorted(
        d
        for d in leaf_dirs
        for child in (REPO_ROOT / d).iterdir()
        if child.name not in IGNORED_NAMES and child.name != ".gitkeep"
    )
    assert polluted == []


def test_no_stray_files_at_repo_root() -> None:
    expected_root = (
        {path.split("/")[0] for path in EXPECTED_DIRS | EXPECTED_FILES} | IGNORED_NAMES | {".git"}
    )
    actual = {p.name for p in REPO_ROOT.iterdir()}
    stray = sorted(actual - expected_root)
    assert stray == [], f"undeclared entries at repo root: {stray}"
