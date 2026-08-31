"""Roadmap 0.7 acceptance tests for scripts/new_iteration.py.

Covers the task DoD: produced tree diffs clean vs the checked-in expected-tree
fixture; fresh iteration validates green against the registered iteration
schema; duplicate same-ID calls fail loudly; invalid IDs are rejected; the
single-in-progress rule is enforced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from conftest import FIXTURES_DIR

EXPECTED_TREE = FIXTURES_DIR / "expected-iteration-tree.txt"


def produced_paths(iteration_dir: Path) -> list[str]:
    return sorted(p.relative_to(iteration_dir).as_posix() for p in iteration_dir.rglob("*"))


def read_iteration(iteration_dir: Path) -> dict[str, Any]:
    document: Any = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert isinstance(document, dict)
    return document


def test_produced_tree_diffs_clean_vs_fixture(new_iteration: Any, tmp_path: Path) -> None:
    iteration_dir = new_iteration.scaffold_iteration(
        "2026-08-acceptance-check", "ui", tmp_path / "iterations"
    )
    expected = EXPECTED_TREE.read_text().splitlines()
    assert produced_paths(iteration_dir) == expected


def test_fresh_iteration_validates_green_via_registry(new_iteration: Any, tmp_path: Path) -> None:
    iteration_dir = new_iteration.scaffold_iteration(
        "2026-08-validate-green", "ui", tmp_path / "iterations"
    )
    document = read_iteration(iteration_dir)
    binding = new_iteration.validate_artifact(
        "iterations/2026-08-validate-green/iteration.yaml",
        document,
        new_iteration.REGISTRY_PATH,
    )
    assert binding["schema"] == "scripts/schemas/iteration.schema.json"


def test_registry_binding_matches_data_model_placement(
    new_iteration: Any,
) -> None:
    _FTD = ".agents/skills/functional-test-design/schemas/"
    bindings = {b["artifact"]: b for b in new_iteration.load_registry(new_iteration.REGISTRY_PATH)}
    expected_schemas = {
        "iteration": "scripts/schemas/iteration.schema.json",
        "requirements": _FTD + "requirements.schema.json",
        "exemptions": "scripts/schemas/exemptions.schema.json",
        "test_points": _FTD + "test_points.schema.json",
        "functional_cases": _FTD + "functional_cases.schema.json",
        "api_spec": ".agents/skills/api-test-design/schemas/api_spec.schema.json",
        "api_cases": ".agents/skills/api-test-design/schemas/api_cases.schema.json",
        "traceability": "scripts/schemas/traceability.schema.json",
        "run_summary": "scripts/schemas/run_summary.schema.json",
        "execution_manifest": "scripts/schemas/execution_manifest.schema.json",
        "medusa_source": "scripts/schemas/medusa_source.schema.json",
    }
    assert set(bindings) == (set(expected_schemas) | {"source_payload"})
    for artifact, schema in expected_schemas.items():
        binding = bindings[artifact]
        assert binding["path_pattern"].startswith("iterations/"), artifact
        assert binding["schema"] == schema, artifact
    payload = bindings["source_payload"]
    assert "any_of" in payload and "schema" not in payload
    schema = json.loads(
        (new_iteration.REPO_ROOT / "scripts/schemas/iteration.schema.json").read_text()
    )
    assert schema["properties"]["schema_version"] == {"const": "1.0"}
    assert "created" in schema["properties"]["state"]["enum"]


@pytest.mark.parametrize(
    "bad_id",
    [
        "ab",  # too short (min 3)
        "a" * 65,  # too long (max 64)
        "2026_08_invalid",  # underscore not allowed
        "-leading-hyphen",  # must start alnum
        "Uppercase-Id",  # lowercase only
        "",  # empty
    ],
)
def test_invalid_iteration_ids_rejected(new_iteration: Any, tmp_path: Path, bad_id: str) -> None:
    with pytest.raises(new_iteration.NewIterationError, match="invalid iteration_id"):
        new_iteration.scaffold_iteration(bad_id, "ui", tmp_path / "iterations")


def test_too_long_id_rejected_with_limit_message(new_iteration: Any, tmp_path: Path) -> None:
    with pytest.raises(new_iteration.NewIterationError, match="3-64 chars"):
        new_iteration.scaffold_iteration("a" * 65, "ui", tmp_path / "iterations")


def test_duplicate_same_id_call_fails_loudly(new_iteration: Any, tmp_path: Path) -> None:
    iterations_dir = tmp_path / "iterations"
    new_iteration.scaffold_iteration("2026-08-duplicate", "ui", iterations_dir)
    with pytest.raises(new_iteration.NewIterationError, match="already exists"):
        new_iteration.scaffold_iteration("2026-08-duplicate", "ui", iterations_dir)


def test_second_in_progress_iteration_rejected(new_iteration: Any, tmp_path: Path) -> None:
    iterations_dir = tmp_path / "iterations"
    new_iteration.scaffold_iteration("2026-08-first", "ui", iterations_dir)
    with pytest.raises(new_iteration.NewIterationError, match="2026-08-first"):
        new_iteration.scaffold_iteration("2026-08-second", "ui", iterations_dir)


@pytest.mark.parametrize("terminal_state", ["accepted", "merged"])
def test_terminal_iteration_does_not_block_new_one(
    new_iteration: Any, tmp_path: Path, terminal_state: str
) -> None:
    iterations_dir = tmp_path / "iterations"
    first = new_iteration.scaffold_iteration("2026-08-done", "ui", iterations_dir)
    document = read_iteration(first)
    document["state"] = terminal_state
    (first / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    second = new_iteration.scaffold_iteration("2026-08-next", "api", iterations_dir)
    assert read_iteration(second)["state"] == "created"


def test_blocked_iteration_counts_as_in_progress(new_iteration: Any, tmp_path: Path) -> None:
    iterations_dir = tmp_path / "iterations"
    first = new_iteration.scaffold_iteration("2026-08-blocked", "ui", iterations_dir)
    document = read_iteration(first)
    document["state"] = "blocked"
    document["blocked_reason"] = "escalated self-debug"
    (first / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(new_iteration.NewIterationError, match="still non-terminal"):
        new_iteration.scaffold_iteration("2026-08-after", "ui", iterations_dir)


def test_branch_declaration_ui_and_api(new_iteration: Any, tmp_path: Path) -> None:
    iterations_dir = tmp_path / "iterations"
    ui = new_iteration.scaffold_iteration("2026-08-ui-branch", "ui", iterations_dir)
    assert read_iteration(ui)["branches"] == {"ui": True, "api": False}


def test_hybrid_branch_declaration_is_schema_invalid(new_iteration: Any, tmp_path: Path) -> None:
    """v1 forbids ui+api together; the schema oneOf must reject a tampered file."""
    iterations_dir = tmp_path / "iterations"
    iteration_dir = new_iteration.scaffold_iteration("2026-08-hybrid", "ui", iterations_dir)
    document = read_iteration(iteration_dir)
    document["branches"] = {"ui": True, "api": True}
    with pytest.raises(new_iteration.NewIterationError, match="branches"):
        new_iteration.validate_artifact(
            "iterations/2026-08-hybrid/iteration.yaml",
            document,
            new_iteration.REGISTRY_PATH,
        )


def test_scaffolded_iteration_yaml_carries_placeholder_statuses(
    new_iteration: Any, tmp_path: Path
) -> None:
    iteration_dir = new_iteration.scaffold_iteration(
        "2026-08-placeholders", "ui", tmp_path / "iterations"
    )
    document = read_iteration(iteration_dir)
    assert document["state"] == "created"
    assert document["blocked_reason"] is None
    for artifact, status in document["artifacts"].items():
        assert status == {"status": "not_started", "input_sha256": None}, artifact
    assert document["approvals"] == []
    assert document["events"] == []
    assert document["source_manifest"] == []


def test_unregistered_path_is_refused_by_registry_path(new_iteration: Any, tmp_path: Path) -> None:
    with pytest.raises(new_iteration.NewIterationError, match="unregistered artifact path"):
        new_iteration.validate_artifact(
            "iterations/2026-08-stray/notes.yaml",
            {"schema_version": "1.0"},
            new_iteration.REGISTRY_PATH,
        )


def test_force_with_wrong_confirmation_aborts(
    new_iteration: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    iterations_dir = tmp_path / "iterations"
    iteration_dir = new_iteration.scaffold_iteration("2026-08-force-me", "ui", iterations_dir)
    marker = iteration_dir / "iteration.yaml"
    before = marker.read_text()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "not-the-id")
    assert (
        new_iteration.main(["2026-08-force-me", "--force", "--iterations-dir", str(iterations_dir)])
        == 2
    )
    assert "aborting" in capsys.readouterr().err
    assert marker.read_text() == before


def test_force_with_typed_confirmation_rescaffolds(
    new_iteration: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    iterations_dir = tmp_path / "iterations"
    iteration_dir = new_iteration.scaffold_iteration("2026-08-force-me", "ui", iterations_dir)
    (iteration_dir / "runs" / "leftover.txt").write_text("stale scratch")
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2026-08-force-me")
    assert (
        new_iteration.main(["2026-08-force-me", "--force", "--iterations-dir", str(iterations_dir)])
        == 0
    )
    assert "scaffolded" in capsys.readouterr().out
    assert read_iteration(iteration_dir)["state"] == "created"
    assert not (iteration_dir / "runs" / "leftover.txt").exists()


def test_duplicate_via_cli_exit_code(new_iteration: Any, tmp_path: Path, capsys: Any) -> None:
    iterations_dir = tmp_path / "iterations"
    assert new_iteration.main(["2026-08-cli", "--iterations-dir", str(iterations_dir)]) == 0
    assert new_iteration.main(["2026-08-cli", "--iterations-dir", str(iterations_dir)]) == 1
    assert "already exists" in capsys.readouterr().err
