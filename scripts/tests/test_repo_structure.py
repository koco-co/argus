"""Roadmap 0.8 acceptance test: repo skeleton matches ARCHITECTURE §2 exactly.

The doc tree is the single structural authority (ARCHITECTURE §2); this test
is the structural diff. Governed roots may not sprout undeclared children —
new structure enters the docs first, then this expected set.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

SKILL_NAMES = (
    "functional-test-design",
    "api-test-design",
    "web-automation-generation",
    "api-automation-generation",
    "self-debug-runner",
    "skill-self-optimizer",
)

SKILL_REQUIRED_CONTRACTS = {
    "functional-test-design": (
        "traceability.yaml",
        "created",
        "requirements_clarifying",
        "--stage exemptions",
        "functional_cases_generating",
        "functional_cases_exported",
    ),
    "api-test-design": (
        "--stage exemptions",
        "requirements_mapped",
        "spec_normalizing",
        "spec_valid",
        "api_cases_generating",
        "api_cases_exported",
    ),
    "web-automation-generation": (
        "functional_cases_exported",
        "web_automation_generating",
        "web_automation_generated",
    ),
    "api-automation-generation": (
        "api_cases_exported",
        "api_automation_generating",
        "api_automation_generated",
    ),
    "self-debug-runner": (
        "side_effect=creates/deletes",
        "fresh reset",
        "scripts/classify_failure.py",
        "scripts/self_debug_helper.py",
    ),
    "skill-self-optimizer": (
        "golden baseline",
        "scripts/check_skill_golden.py",
        "--stage skill_change",
        "--action approved",
    ),
}

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
    *(
        f".agents/skills/{skill}/versions/baselines/1.0.0"
        for skill in (
            "functional-test-design",
            "api-test-design",
            "web-automation-generation",
            "api-automation-generation",
        )
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
    "automation/web/tests/harness/test_harness_smoke.py",
    "automation/web/tests/harness/test_prod_gate_probe.py",
    "scripts/orphan-allowlist.yaml",
    "scripts/new_iteration.py",
    "scripts/_registry_lib.py",
    "scripts/schema_registry.yaml",
    "scripts/schemas/iteration.schema.json",
    "scripts/validate_schema.py",
    "scripts/validate_iteration.py",
    "scripts/check_db_readonly.py",
    "scripts/check_secrets.py",
    "scripts/check_skill_golden.py",
    "scripts/finalize_merge.py",
    "scripts/notify.py",
    ".github/workflows/ci.yml",
    ".github/workflows/regression.yml",
    ".github/dependabot.yml",
    "target-app/Dockerfile",
    "target-app/compose.yaml",
    "target-app/medusa.lock.yaml",
    "shared/testdata/seed-registry.yaml",
    "shared/config/__init__.py",
    "shared/config/settings.py",
    "shared/db/__init__.py",
    "shared/db/readonly_client.py",
    "shared/assertions/__init__.py",
    "shared/assertions/db_asserts.py",
    *(
        f".agents/skills/{skill}/versions/baselines/1.0.0/manifest.yaml"
        for skill in (
            "functional-test-design",
            "api-test-design",
            "web-automation-generation",
            "api-automation-generation",
        )
    ),
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
    "plugins/_interface": {"contract.md", "schemas"},
    "config": {"env.example.yaml", "notify.example.yaml"},
    "automation": {"conftest.py", "web", "mobile", "miniprogram", "api", "perf"},
    "automation/web": {"conftest.py", "pages", "components", "fixtures", "tests"},
    "automation/mobile": {"android", "ios", "screens", "tests"},
    "automation/miniprogram": {"pages", "tests"},
    "automation/api": {"conftest.py", "clients", "models", "tests", "har"},
    "automation/perf": {"locustfiles", "scenarios"},
    "shared": {"utils", "assertions", "config", "db", "notify", "testdata"},
    # junit.xml 是回归工作流的运行时产物，和 Allure 目录一样被 gitignore。
    "reports": {"allure-results", "allure-report", "junit.xml"},
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
        "check_skill_golden.py",
        "check_layering.py",
        "check_pom_boundary.py",
        "check_test_markers.py",
        "check_api_models.py",
        "check_prod_scope.py",
        "check_orphan_tests.py",
        "render_md.py",
        "export_xmind.py",
        "export_xlsx.py",
        "check_coverage.py",
        "check_api_coverage.py",
        "check_patch_scope.py",
        "classify_failure.py",
        "self_debug_helper.py",
        "notify.py",
        "finalize_merge.py",
        "weekly_escalation.py",
        "check_functional_expectations.py",
        "_writers.py",
        "record_event.py",
        "record_approval.py",
        "reopen_iteration.py",
        "run_plugin.py",
        "_target_app.py",
        "target_app_up.py",
        "target_app_seed.py",
        "target_app_reset.py",
        "target_app_healthcheck.py",
        "target_app_canary.py",
        "target_app_down.py",
        "orphan-allowlist.yaml",
        "schemas",
        "tests",
    },
    "scripts/tests": {
        "conftest.py",
        "fixtures",
        "test_writers.py",
        "test_run_plugin.py",
        "test_target_app_harness.py",
        "test_settings.py",
        "test_readonly_client.py",
        "test_automation_conftest.py",
        "test_classify_failure.py",
        "test_self_debug_helper.py",
        "test_notify.py",
        "test_finalize_merge.py",
        "test_weekly_escalation.py",
        "test_knowledge.py",
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
        "test_check_skill_golden.py",
        "test_check_layering.py",
        "test_check_prod_scope.py",
        "test_check_orphan_tests.py",
    },
    "target-app": {
        "Dockerfile",
        "compose.yaml",
        "medusa.lock.yaml",
        "overrides",
        "runtime.env",
        "seed-state.yaml",
    },
}


def test_expected_directories_exist() -> None:
    missing = sorted(d for d in EXPECTED_DIRS if not (REPO_ROOT / d).is_dir())
    assert missing == []


def test_expected_files_exist() -> None:
    missing = sorted(f for f in EXPECTED_FILES if not (REPO_ROOT / f).is_file())
    assert missing == []


def test_executable_checkers_invoke_main_from_cli() -> None:
    """所有 check_*.py 门禁都必须在命令行调用时真正执行。"""
    missing = []
    for path in sorted((REPO_ROOT / "scripts").glob("check_*.py")):
        source = path.read_text(encoding="utf-8")
        if "def main(" in source and 'if __name__ == "__main__":' not in source:
            missing.append(path.name)
    assert missing == []


def test_artifact_upload_action_uses_node24_release() -> None:
    """上传证据的 Action 必须使用已迁移到 Node 24 的主版本。"""
    workflow = (REPO_ROOT / ".github/workflows/regression.yml").read_text(encoding="utf-8")
    match = re.search(
        r"actions/upload-artifact@(?P<sha>[0-9a-f]{40})\s+#\s+v(?P<major>\d+)", workflow
    )
    assert match is not None
    assert int(match.group("major")) >= 7


def test_architecture_tree_and_ci_example_match_real_entrypoints() -> None:
    """目录唯一权威不得重新引入不存在、重复或过期的脚本入口。"""
    architecture = (REPO_ROOT / "docs/spec/architecture/ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    tree = architecture.split("## 3. Module Decoupling Rules", 1)[0]
    assert tree.count("classify_failure.py") == 1
    assert tree.count("self_debug_helper.py") == 1
    assert "find_affected_modules.py" not in tree
    assert "├── Jenkinsfile" not in tree
    assert "self_debug_helper.py record-ci-auto" in architecture
    assert "self_debug_helper.py archive --dest" not in architecture


def test_keeper_dirs_hold_a_gitkeep() -> None:
    empty = sorted(d for d in KEEPER_DIRS if not (REPO_ROOT / d / ".gitkeep").is_file())
    assert empty == []


@pytest.mark.parametrize("root", sorted(GOVERNED_CHILDREN))
def test_governed_roots_have_no_undeclared_children(root: str) -> None:
    root_path = REPO_ROOT / root
    assert root_path.is_dir(), f"governed root {root} missing"
    actual = {p.name for p in root_path.iterdir() if p.name not in IGNORED_NAMES}
    if root == "config":
        # env.<name>.yaml 是 M8 生成且 gitignored 的运行时文件，不属于仓库结构漂移。
        actual = {
            name for name in actual if not name.startswith("env.") or name == "env.example.yaml"
        }
    declared = GOVERNED_CHILDREN[root]
    undeclared = sorted(actual - declared)
    assert undeclared == [], f"undeclared entries under {root}: {undeclared}"


def test_unimplemented_automation_leaf_dirs_are_empty_beyond_keepers() -> None:
    """尚未交付的端类型目录只能保留占位文件。

    Web/API 已进入生成阶段，模块子目录及 conftest 属于预期产物，不再应用
    初始化阶段的“必须为空”约束。
    """
    leaf_dirs = [
        d
        for d in EXPECTED_DIRS
        if d.startswith(("automation/", "shared/"))
        and d
        not in {
            "shared/testdata",
            "shared/config",
            "shared/db",
            "shared/assertions",
            "shared/notify",
            "automation/web/pages",
            "automation/web/components",
            "automation/web/fixtures",
            "automation/web/tests",
            "automation/api/clients",
            "automation/api/models",
            "automation/api/tests",
            "automation/api/har",
        }
        and (REPO_ROOT / d).is_dir()
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


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_entrypoint_matches_agent_skills_contract(skill_name: str) -> None:
    """六个项目级 Skill 都必须提供最小、可发现且版本化的入口。"""
    path = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert set(metadata) == {"name", "description", "metadata"}
    assert metadata["name"] == skill_name
    assert 1 <= len(metadata["description"]) <= 1024
    assert metadata["metadata"] == {"version": "1.0.0"}
    assert "# Outcome" in body
    assert "## Steps" in body
    assert "## Guardrails" in body


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_entrypoint_contains_required_project_contracts(skill_name: str) -> None:
    """关键状态、批准和证据义务必须直接写入 Skill，不能依赖模型猜测。"""
    path = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    missing = [token for token in SKILL_REQUIRED_CONTRACTS[skill_name] if token not in text]
    assert missing == [], f"{skill_name} 缺少项目契约：{missing}"


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_claude_skill_adapter_is_relative_in_repo_symlink(skill_name: str) -> None:
    """Claude 适配入口只能链接到仓库内的唯一 Skill 规范源。"""
    link = REPO_ROOT / ".claude" / "skills" / skill_name
    source = REPO_ROOT / ".agents" / "skills" / skill_name
    assert link.is_symlink()
    assert not link.readlink().is_absolute()
    assert link.resolve() == source.resolve()
