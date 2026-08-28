"""Phase 2：真实子进程加载、隔离文件、统一 Schema 和安全失败路径。"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import FIXTURES_DIR, SCRIPTS_DIR, _load_script


@pytest.fixture()
def runner() -> Any:
    return _load_script("run_plugin")


@pytest.fixture()
def iteration(tmp_path: Path, new_iteration: Any) -> Path:
    root = tmp_path / "iterations/test-fixture-plugin"
    (root / "00-raw").mkdir(parents=True)
    (root / "iteration.yaml").write_text(
        yaml.safe_dump(new_iteration.build_iteration_document(root.name, "ui"))
    )
    return root


def fixture(name: str) -> Path:
    return FIXTURES_DIR / "schemas" / name


def installed_plugin(tmp_path: Path, body: str, **extra: Any) -> tuple[Path, dict[str, Any]]:
    directory = tmp_path / "plugins"
    directory.mkdir(exist_ok=True)
    (directory / "fixture.py").write_text(body, encoding="utf-8")
    entry = {"name": "fixture", "path": "fixture.py", "source_type": "paste", **extra}
    registry = directory / "registry.yaml"
    registry.write_text(yaml.safe_dump({"plugins": [entry]}), encoding="utf-8")
    return registry, entry


def test_unknown_plugin_cli_exits_nonzero_with_actionable_message() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_plugin.py"), "nonexistent", "ref"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "plugins/registry.yaml" in result.stderr
    assert "--payload" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("name", "exit_code"),
    [
        ("requirement_source_payload--paste.valid.yaml", 0),
        ("api_source_payload--openapi.valid.yaml", 0),
        ("requirement_source_payload--error.valid.yaml", 1),
        ("api_source_payload--error.valid.yaml", 1),
        ("requirement_source_payload--error-with-content.invalid.yaml", 1),
        ("api_source_payload--error-with-content.invalid.yaml", 1),
        ("requirement_source_payload--bad-date-time.invalid.yaml", 1),
        # 此样本仅对 API Schema 非法；其 jira 类型仍是合法需求信封。
        ("api_source_payload--wrong-source-type.invalid.yaml", 0),
        ("requirement_source_payload--unknown-source.invalid.yaml", 1),
    ],
)
def test_import_retains_success_error_and_invalid_envelopes(
    runner: Any, iteration: Path, name: str, exit_code: int
) -> None:
    source = fixture(name)
    assert runner.main(["--payload", str(source), "--iteration", str(iteration)]) == exit_code
    output = iteration / "00-raw/source-payload.yaml"
    assert yaml.safe_load(output.read_text()) == yaml.safe_load(source.read_text())


def test_validation_observes_the_persisted_file(
    runner: Any, iteration: Path, monkeypatch: Any, capsys: Any
) -> None:
    validate = runner.validate_one
    calls: list[Path] = []

    def inspect_disk(path: Path, registry: Path) -> list[str]:
        assert path.is_file()
        assert yaml.safe_load(path.read_text())["fetched_at"] == "2026-13-45T99:00:00Z"
        calls.append(path)
        return validate(path, registry)

    monkeypatch.setattr(runner, "validate_one", inspect_disk)
    source = fixture("requirement_source_payload--bad-date-time.invalid.yaml")
    assert runner.main(["--payload", str(source), "--iteration", str(iteration)]) == 1
    assert calls == [iteration / "00-raw/source-payload.yaml"]
    assert "fetched_at" in capsys.readouterr().err


def test_same_input_is_idempotent_and_different_input_is_never_overwritten(
    runner: Any, iteration: Path
) -> None:
    arguments = [
        "--payload",
        str(fixture("requirement_source_payload--paste.valid.yaml")),
        "--iteration",
        str(iteration),
    ]
    assert runner.main(arguments) == 0
    output = iteration / "00-raw/source-payload.yaml"
    before = output.stat().st_mtime_ns, output.read_bytes()
    assert runner.main(arguments) == 0
    assert (output.stat().st_mtime_ns, output.read_bytes()) == before
    arguments[1] = str(fixture("api_source_payload--openapi.valid.yaml"))
    assert runner.main(arguments) == 1
    assert (output.stat().st_mtime_ns, output.read_bytes()) == before


def test_registered_plugin_executes_real_child_process(
    runner: Any, tmp_path: Path, iteration: Path
) -> None:
    envelope = yaml.safe_load(fixture("requirement_source_payload--paste.valid.yaml").read_text())
    body = f"def fetch(source_ref, *, credentials):\n    return {envelope!r}\n"
    registry, _ = installed_plugin(tmp_path, body)
    assert (
        runner.main(
            ["fixture", "reference", "--registry", str(registry), "--iteration", str(iteration)]
        )
        == 0
    )
    assert yaml.safe_load((iteration / "00-raw/source-payload.yaml").read_text()) == envelope


@pytest.mark.parametrize("mode", ["return", "raise"])
def test_plugin_credentials_never_reach_disk_or_logs(
    runner: Any, tmp_path: Path, iteration: Path, monkeypatch: Any, capsys: Any, mode: str
) -> None:
    secret_value = "fixture-private-value"
    monkeypatch.setenv("ARGUS_FIXTURE_CREDENTIAL", secret_value)
    payload = yaml.safe_load(fixture("requirement_source_payload--paste.valid.yaml").read_text())
    body = "def fetch(source_ref, *, credentials):\n    print(credentials['key'])\n"
    if mode == "raise":
        body += "    raise RuntimeError(credentials['key'])\n"
    else:
        body += f"    envelope = {payload!r}\n"
        body += "    envelope['content'] = credentials['key']\n    return envelope\n"
    registry, _ = installed_plugin(
        tmp_path, body, credentials_env={"key": "ARGUS_FIXTURE_CREDENTIAL"}
    )
    assert (
        runner.main(
            ["fixture", "reference", "--registry", str(registry), "--iteration", str(iteration)]
        )
        == 1
    )
    output = iteration / "00-raw/source-payload.yaml"
    assert "error" in yaml.safe_load(output.read_text())
    captured = capsys.readouterr()
    assert secret_value not in output.read_text() + captured.out + captured.err
    assert runner.validate_one(output, runner.DEFAULT_REGISTRY) == []


def test_hanging_plugin_is_killed_and_persists_error(
    runner: Any, tmp_path: Path, iteration: Path, monkeypatch: Any
) -> None:
    registry, _ = installed_plugin(
        tmp_path, "import time\ndef fetch(source_ref, *, credentials):\n    time.sleep(10)\n"
    )
    monkeypatch.setattr(runner, "CONNECT_TIMEOUT", 0.2)
    monkeypatch.setattr(runner, "READ_TIMEOUT", 0.2)
    assert (
        runner.main(
            ["fixture", "reference", "--registry", str(registry), "--iteration", str(iteration)]
        )
        == 1
    )
    payload = yaml.safe_load((iteration / "00-raw/source-payload.yaml").read_text())
    assert payload["error"]["code"] == "fetch_timeout"


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://[::1]", "http://169.254.169.254"])
def test_nonpublic_url_never_reaches_plugin(
    runner: Any, tmp_path: Path, iteration: Path, url: str
) -> None:
    registry, _ = installed_plugin(tmp_path, "raise RuntimeError('must not load')\n")
    assert (
        runner.main(["fixture", url, "--registry", str(registry), "--iteration", str(iteration)])
        == 1
    )
    payload = yaml.safe_load((iteration / "00-raw/source-payload.yaml").read_text())
    assert payload["error"]["code"] == "unsafe_or_unavailable_source"


@pytest.mark.parametrize("path", ["../outside.py", "/tmp/outside.py", "missing.py"])
def test_registry_path_cannot_escape_plugin_root(runner: Any, tmp_path: Path, path: str) -> None:
    registry, entry = installed_plugin(tmp_path, "")
    entry["path"] = path
    registry.write_text(yaml.safe_dump({"plugins": [entry]}))
    with pytest.raises(runner.PluginError, match="plugins/"):
        runner.resolve_plugin("fixture", registry)


def test_output_cannot_follow_symlink(runner: Any, tmp_path: Path, iteration: Path) -> None:
    foreign = tmp_path / "foreign.yaml"
    foreign.write_text("unchanged")
    (iteration / "00-raw/source-payload.yaml").symlink_to(foreign)
    source = fixture("requirement_source_payload--paste.valid.yaml")
    assert runner.main(["--payload", str(source), "--iteration", str(iteration)]) == 1
    assert foreign.read_text() == "unchanged"


def test_import_does_not_create_missing_iteration(runner: Any, tmp_path: Path) -> None:
    path = tmp_path / "iterations/test-fixture-missing"
    assert (
        runner.main(
            [
                "--payload",
                str(fixture("requirement_source_payload--paste.valid.yaml")),
                "--iteration",
                str(path),
            ]
        )
        == 1
    )
    assert not path.exists()


def test_compressed_input_limit_applies_after_decompression(
    runner: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    compressed = tmp_path / "payload.yaml.gz"
    compressed.write_bytes(gzip.compress(b"x" * 1000))
    monkeypatch.setattr(runner, "MAX_BYTES", 100)
    with pytest.raises(runner.PluginError, match="解压后"):
        runner.read_payload(compressed)


def test_secret_bearing_import_is_rejected_before_persistence(
    runner: Any, tmp_path: Path, iteration: Path
) -> None:
    source = tmp_path / "unsafe.yaml"
    source.write_text(json.dumps({"content": {"password": "fixture-private-value"}}))
    assert runner.main(["--payload", str(source), "--iteration", str(iteration)]) == 1
    assert not (iteration / "00-raw/source-payload.yaml").exists()


def test_recursive_yaml_is_rejected_without_traceback(
    runner: Any, tmp_path: Path, iteration: Path, capsys: Any
) -> None:
    source = tmp_path / "recursive.yaml"
    source.write_text("content: &cycle [*cycle]\n")
    assert runner.main(["--payload", str(source), "--iteration", str(iteration)]) == 1
    assert "循环引用" in capsys.readouterr().err
    assert not (iteration / "00-raw/source-payload.yaml").exists()


def test_plugin_cannot_return_another_registered_source_type(
    runner: Any, tmp_path: Path, iteration: Path, capsys: Any
) -> None:
    envelope = yaml.safe_load(fixture("api_source_payload--openapi.valid.yaml").read_text())
    registry, _ = installed_plugin(
        tmp_path, f"def fetch(source_ref, *, credentials):\n    return {envelope!r}\n"
    )
    assert (
        runner.main(
            ["fixture", "reference", "--registry", str(registry), "--iteration", str(iteration)]
        )
        == 1
    )
    assert "source_type" in capsys.readouterr().err
    assert (iteration / "00-raw/source-payload.yaml").is_file()
