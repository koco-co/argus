"""Roadmap 1.13 acceptance tests for scripts/check_secrets.py.

DoD: seeded patterns (Bearer/JWT/AKIA-style/DSN-password) caught; clean
fixtures pass; CHANGE_ME placeholders never trip; line-level
`# secret-ok: <reason>` exemptions honored; binary files skipped.

NOTE: the sample secret VALUES below are assembled from string fragments at
runtime on purpose - this test file itself must not contain literal
credential-shaped text (the framework scans its own sources).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script

JWT_A, JWT_B, JWT_C = (
    "eyJhbGciOiJIUzI1NiJ9",
    "eyJzIjoiMSJ9",
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c",
)


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_secrets")


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "iterations" / "2026-08-sec" / "00-raw" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _problems(checker: Any, path: Path) -> list[str]:
    report = checker.Report()
    checker.scan_file(path, report)
    return report.problems


def test_clean_text_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "notes.md",
        """\
        The user can Bearer-free login via SSO.
        Password policy: minimum 8 chars. See docs.
        DSN shape: postgresql://user:CHANGE_ME@host:5432/db
        """,
    )
    assert _problems(checker, path) == []


def test_bearer_token_caught(checker: Any, tmp_path: Path) -> None:
    token = "AbCdEf" + "1234567890" + "abcdefGHI"
    path = _write(tmp_path, "notes.md", f"curl -H 'Authorization: Bearer {token}' /api\n")
    problems = _problems(checker, path)
    assert any("'bearer-token'" in p for p in problems)


def test_jwt_caught(checker: Any, tmp_path: Path) -> None:
    path = _write(tmp_path, "notes.md", f"token: {JWT_A}.{JWT_B}.{JWT_C}\n")
    problems = _problems(checker, path)
    assert any("'jwt'" in p for p in problems)


def test_akia_key_caught(checker: Any, tmp_path: Path) -> None:
    key = "AKIA" + "IOSFO" + "DNN7" + "EXAM" + "PLE"  # assembled: no literal cloud key
    path = _write(tmp_path, "notes.md", f"aws key {key} in the dump\n")
    problems = _problems(checker, path)
    assert any("'aws-access-key'" in p for p in problems)


def test_dsn_password_caught(checker: Any, tmp_path: Path) -> None:
    dsn = "postgresql://admin:" + "S3cr" + "etPw" + "@db.internal:5432/store"
    path = _write(tmp_path, "notes.md", f"connect via {dsn}\n")
    problems = _problems(checker, path)
    assert any("'dsn-password'" in p for p in problems)


def test_generic_key_value_caught(checker: Any, tmp_path: Path) -> None:
    value = "abcd" + "1234" + "efgh" + "5678"
    path = _write(tmp_path, "notes.md", f'api_key = "{value}"\n')
    problems = _problems(checker, path)
    assert any("'generic-key-value'" in p for p in problems)


def test_private_key_block_caught(checker: Any, tmp_path: Path) -> None:
    header = "-----BEGIN " + "RSA PRIVATE KEY-----"
    path = _write(tmp_path, "notes.md", f"{header}\nMIIEow...\n")
    problems = _problems(checker, path)
    assert any("'private-key-block'" in p for p in problems)


def test_change_me_placeholder_ignored(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "notes.md",
        "dsn: postgresql://CHANGE_ME_ROLE:CHANGE_ME@CHANGE_ME_HOST:5432/db\n"
        'password: "CHANGE_' + "ME_VALUE_" + '123"\n',
    )
    assert _problems(checker, path) == []


def test_secret_ok_escape_honored(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "notes.md",
        f"token: {JWT_A}.{JWT_B}.{JWT_C}  # secret-ok: dummy test fixture value\n",
    )
    assert _problems(checker, path) == []


def test_binary_file_skipped(checker: Any, tmp_path: Path) -> None:
    path = tmp_path / "iterations" / "2026-08-sec" / "00-raw" / "dump.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\x00\xff\xfe Bearer " + b"AbCdEf" + b"1234567890" + b"abcdefGHI"
    path.write_bytes(payload)
    assert _problems(checker, path) == []
