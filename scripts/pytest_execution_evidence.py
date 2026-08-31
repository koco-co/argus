"""Pytest plugin that records exact collected/executed nodeids for CI evidence.

The plugin is opt-in (``-p scripts.pytest_execution_evidence``) and writes only
when ``ARGUS_EXECUTED_NODEIDS`` is set. It records outcomes separately from
JUnit so an iteration manifest can prove that its selected traceability nodes
were not silently skipped.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_MAX_BYTES = 8 * 1024 * 1024
_NODEID_PREFIX = "automation/"
_COLLECTED_NODEIDS: set[str] = set()
_NODEIDS: set[str] = set()
_OUTCOMES: dict[str, str] = {}


def _safe_nodeid(nodeid: object) -> bool:
    if not isinstance(nodeid, str) or not nodeid.startswith(_NODEID_PREFIX):
        return False
    if "\x00" in nodeid or "\r" in nodeid or "\n" in nodeid or "\\" in nodeid or "::" not in nodeid:
        return False
    file_part, test_part = nodeid.split("::", 1)
    return bool(file_part and test_part and ".." not in Path(file_part).parts)


def _safe_output_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or "\x00" in value or "\\" in value or ".." in path.parts:
        raise RuntimeError("ARGUS_EXECUTED_NODEIDS must be a safe relative path")
    current = Path.cwd()
    for part in path.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise RuntimeError("ARGUS_EXECUTED_NODEIDS must not pass through a symlink")
    if path.is_symlink():
        raise RuntimeError("ARGUS_EXECUTED_NODEIDS must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise RuntimeError("ARGUS_EXECUTED_NODEIDS must not be a symlink")
    return path


def pytest_configure(config: Any) -> None:
    del config
    _COLLECTED_NODEIDS.clear()
    _NODEIDS.clear()
    _OUTCOMES.clear()


def pytest_collection_finish(session: Any) -> None:
    for item in session.items:
        nodeid = getattr(item, "nodeid", None)
        if not isinstance(nodeid, str) or not nodeid.startswith(_NODEID_PREFIX):
            continue
        if not _safe_nodeid(nodeid):
            raise RuntimeError(f"unsafe pytest nodeid: {nodeid!r}")
        _COLLECTED_NODEIDS.add(nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    nodeid = report.nodeid
    if not isinstance(nodeid, str) or not nodeid.startswith(_NODEID_PREFIX):
        return
    if not _safe_nodeid(nodeid):
        raise RuntimeError(f"unsafe pytest nodeid: {nodeid!r}")
    _NODEIDS.add(nodeid)
    # Prefer the call outcome, but retain setup/teardown failures when there is
    # no call phase (for example fixture setup failed).
    current = _OUTCOMES.get(nodeid)
    phase = getattr(report, "when", "call")
    outcome = report.outcome
    if getattr(report, "wasxfail", False):
        outcome = "xpassed" if outcome == "passed" else "xfailed"
    if current in {"failed", "xfailed"} and outcome == "skipped":
        return
    if outcome in {"failed", "xfailed"} or phase == "call" or current is None:
        _OUTCOMES[nodeid] = outcome


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    target = os.environ.get("ARGUS_EXECUTED_NODEIDS")
    if not target:
        return
    path = _safe_output_path(target)
    del session
    document = {
        "schema_version": "1.1",
        "exit_status": exitstatus,
        "collected_nodeids": sorted(_COLLECTED_NODEIDS),
        "nodeids": sorted(_NODEIDS),
        "outcomes": {key: _OUTCOMES[key] for key in sorted(_OUTCOMES)},
    }
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if len(payload) > _MAX_BYTES:
        raise RuntimeError("pytest execution evidence exceeds size limit")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
