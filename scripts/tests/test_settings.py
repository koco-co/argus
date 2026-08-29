"""Roadmap 5.1：环境配置加载与 M8 机械门禁验收。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shared.config import settings


def _env(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _iteration(path: Path, *, api: bool) -> Path:
    path.mkdir(parents=True)
    (path / "iteration.yaml").write_text(
        yaml.safe_dump(
            {
                "branches": {"ui": not api, "api": api},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_guest_config_without_auth_or_db_loads(tmp_path: Path) -> None:
    path = _env(tmp_path / "env.guest.yaml", 'base_url: "http://localhost:8000"\n')
    loaded = settings.load_path(path)
    assert str(loaded.base_url).rstrip("/") == "http://localhost:8000"
    assert loaded.auth is None
    assert loaded.db is None


def test_empty_yaml_is_reported_without_none_crash(tmp_path: Path) -> None:
    path = _env(tmp_path / "env.empty.yaml", "")
    assert settings.check_path(path) == ["base_url: 缺失"]


def test_cli_env_has_precedence_over_test_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _env(config_dir / "env.local.yaml", 'base_url: "http://local.invalid"\n')
    _env(config_dir / "env.ci.yaml", 'base_url: "http://ci.invalid"\n')
    _env(config_dir / "env.prod.yaml", 'base_url: "http://prod.invalid"\n')
    monkeypatch.setenv("TEST_ENV", "prod")

    assert settings.resolve_env_name() == "prod"
    assert settings.resolve_env_name("ci") == "ci"
    assert settings.load_env(cli_flag="ci", config_dir=config_dir).base_url == "http://ci.invalid"


def test_environment_variables_override_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _env(
        tmp_path / "env.local.yaml",
        """\
base_url: http://yaml.invalid
auth:
  username: yaml-user
  password: yaml-pass
cookies: {}
""",
    )
    monkeypatch.setenv("ARGUS_BASE_URL", "http://env.invalid")
    monkeypatch.setenv("ARGUS_API_BASE_URL", "http://api.invalid")
    monkeypatch.setenv("ARGUS_AUTH_USERNAME", "env-user")
    monkeypatch.setenv("ARGUS_AUTH_PASSWORD", "env-pass")
    loaded = settings.load_path(path)
    assert loaded.base_url == "http://env.invalid"
    assert loaded.api_base_url == "http://api.invalid"
    assert loaded.auth is not None
    assert loaded.auth.username == "env-user"
    assert loaded.auth.password.get_secret_value() == "env-pass"


def test_check_lists_exact_api_branch_omissions(tmp_path: Path) -> None:
    path = _env(
        tmp_path / "env.broken.yaml",
        """\
base_url: ftp://bad.example
auth:
  username: ""
db:
  dsn: not-a-dsn
""",
    )
    iteration = _iteration(tmp_path / "iterations" / "api-case", api=True)

    assert settings.check_path(path, iteration) == [
        "base_url: 必须是 http 或 https URL",
        "auth.username: 缺失",
        "auth.password: 缺失",
        "db.dsn: 必须是 PostgreSQL DSN",
        "db.dsn: 配置文件必须用注释声明只读角色",
    ]


def test_check_api_branch_complete_config_passes(tmp_path: Path) -> None:
    path = _env(
        tmp_path / "env.complete.yaml",
        """\
# DB 角色：只读，仅授予 SELECT 权限。
base_url: http://localhost:9000
api_base_url: http://localhost:9000
auth:
  username: api-user
  password: api-pass
db:
  dsn: postgresql://readonly:secret@localhost:5432/medusa
cookies: {}
""",
    )
    iteration = _iteration(tmp_path / "iterations" / "api-case", api=True)
    assert settings.check_path(path, iteration) == []


def test_check_rejects_invalid_optional_api_base_url(tmp_path: Path) -> None:
    path = _env(
        tmp_path / "env.bad-api-url.yaml",
        "base_url: http://localhost:8000\napi_base_url: tcp://localhost:9000\n",
    )
    assert settings.check_path(path) == ["api_base_url: 必须是 http 或 https URL"]


def test_assemble_writes_gitignored_ci_file_without_printing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("ARGUS_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("ARGUS_API_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("ARGUS_AUTH_USERNAME", "ci-user")
    monkeypatch.setenv("ARGUS_AUTH_PASSWORD", "ci-secret")
    monkeypatch.setenv(
        "ARGUS_DB_DSN", "postgresql://argus_readonly:db-secret@localhost:15432/medusa"
    )

    assert settings.main(["assemble", "--env", "ci", "--config-dir", str(config_dir)]) == 0
    output = capsys.readouterr().out
    target = config_dir / "env.ci.yaml"
    assert target.exists()
    assert "ci-secret" not in output
    source = target.read_text(encoding="utf-8")
    assert "只读" in source and "SELECT" in source
    assert yaml.safe_load(source)["auth"]["password"] == "ci-secret"
    iteration = _iteration(tmp_path / "iterations" / "api-case", api=True)
    assert settings.check_path(target, iteration) == []
