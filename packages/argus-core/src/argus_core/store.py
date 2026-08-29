"""版本化迭代 Store：跨进程锁、校验和原子替换。"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import yaml

from .approvals import append_approval  # pyright: ignore[reportMissingImports]
from .models import (  # pyright: ignore[reportMissingImports]
    SCHEMA_VERSION,
    Approval,
    DelegationGrant,
    IterationDocument,
    Workstream,
)
from .state import transition  # pyright: ignore[reportMissingImports]

try:
    import fcntl
except ImportError:  # pragma: no cover - v2 支持的 Unix 运行面使用 fcntl
    fcntl = None

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_T = TypeVar("_T")


class StoreError(RuntimeError):
    """迭代文件不可读、不可写或不满足 v2 契约。"""


class IterationStore:
    """每个 iteration 一个锁域；多个 workstream 可以安全并行提交事务。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.iterations_root = self.project_root / ".argus" / "iterations"

    def path_for(self, iteration_id: str) -> Path:
        if not _ID_PATTERN.fullmatch(iteration_id):
            raise StoreError(f"invalid iteration id: {iteration_id!r}")
        return self.iterations_root / iteration_id / "iteration.yaml"

    def _ensure_safe_directory(self, iteration_yaml: Path) -> None:
        directories = (self.project_root / ".argus", self.iterations_root, iteration_yaml.parent)
        for directory in directories:
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise StoreError(f"iteration directory is not safe: {directory}")
        iteration_yaml.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self, iteration_yaml: Path) -> Iterator[None]:
        self._ensure_safe_directory(iteration_yaml)
        lock_path = iteration_yaml.with_name(f".{iteration_yaml.name}.lock")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise StoreError(f"cannot create iteration lock: {lock_path}") from exc
        with os.fdopen(descriptor, "a+b") as stream:
            if fcntl is None:
                raise StoreError("argus-core requires a POSIX file-locking runtime")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read_unlocked(iteration_yaml: Path) -> IterationDocument:
        if not iteration_yaml.is_file() or iteration_yaml.is_symlink():
            raise StoreError(f"iteration file is missing or symlinked: {iteration_yaml}")
        try:
            raw = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8"))
            return IterationDocument.model_validate(raw)
        except (OSError, UnicodeError, yaml.YAMLError, TypeError, ValueError) as exc:
            raise StoreError(f"invalid v2 iteration document: {iteration_yaml}") from exc

    @staticmethod
    def _write_unlocked(iteration_yaml: Path, document: IterationDocument) -> None:
        if document.schema_version != SCHEMA_VERSION:
            raise StoreError("only the v2.0 iteration schema is writable")
        encoded = yaml.safe_dump(
            document.model_dump(mode="json"),
            sort_keys=False,
            allow_unicode=True,
        ).encode("utf-8")
        mode = iteration_yaml.stat().st_mode & 0o777 if iteration_yaml.exists() else 0o640
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{iteration_yaml.name}.", suffix=".tmp", dir=iteration_yaml.parent
        )
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, mode)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, iteration_yaml)
            try:
                directory = os.open(iteration_yaml.parent, os.O_RDONLY)
            except OSError:
                return
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StoreError(f"cannot atomically write {iteration_yaml}") from exc

    def create(self, iteration_id: str, workstreams: list[Workstream]) -> IterationDocument:
        """创建 v2 文档；不会读取或改写任何 v1 iteration。"""
        iteration_yaml = self.path_for(iteration_id)
        if iteration_yaml.exists():
            raise StoreError(f"iteration already exists: {iteration_id}")
        now = datetime.now(UTC)
        document = IterationDocument(
            iteration_id=iteration_id,
            created_at=now,
            updated_at=now,
            workstreams=workstreams,
        )
        with self._lock(iteration_yaml):
            if iteration_yaml.exists():
                raise StoreError(f"iteration already exists: {iteration_id}")
            self._write_unlocked(iteration_yaml, document)
        return document

    def load(self, iteration_id: str) -> IterationDocument:
        iteration_yaml = self.path_for(iteration_id)
        if not iteration_yaml.is_file() or iteration_yaml.is_symlink():
            raise StoreError(f"iteration file is missing or symlinked: {iteration_yaml}")
        with self._lock(iteration_yaml):
            return self._read_unlocked(iteration_yaml)

    def transact(
        self,
        iteration_id: str,
        mutator: Callable[[IterationDocument], _T],
    ) -> tuple[IterationDocument, _T]:
        """在同一锁内读取、修改、校验和替换；异常时不写半成品。"""
        iteration_yaml = self.path_for(iteration_id)
        if not iteration_yaml.is_file() or iteration_yaml.is_symlink():
            raise StoreError(f"iteration file is missing or symlinked: {iteration_yaml}")
        with self._lock(iteration_yaml):
            document = self._read_unlocked(iteration_yaml)
            result = mutator(document)
            document.revision += 1
            document.updated_at = datetime.now(UTC)
            IterationDocument.model_validate(document)
            self._write_unlocked(iteration_yaml, document)
            return document, result

    def approve(self, iteration_id: str, approval: Approval) -> IterationDocument:
        document, _ = self.transact(
            iteration_id,
            lambda current: append_approval(current, approval),
        )
        return document

    def grant(self, iteration_id: str, grant: DelegationGrant) -> IterationDocument:
        def mutate(document: IterationDocument) -> None:
            if document.delegation is not None and document.delegation != grant:
                raise StoreError("iteration already has a different delegation grant")
            document.delegation = grant

        document, _ = self.transact(iteration_id, mutate)
        return document

    def transition(
        self,
        iteration_id: str,
        workstream_id: str,
        target: str,
        actor: str,
        reason: str | None = None,
    ) -> IterationDocument:
        from .models import Actor, WorkstreamStatus  # pyright: ignore[reportMissingImports]

        def mutate(document: IterationDocument) -> None:
            transition(
                document,
                workstream_id,
                WorkstreamStatus(target),
                Actor(actor),
                reason=reason,
            )

        document, _ = self.transact(iteration_id, mutate)
        return document
