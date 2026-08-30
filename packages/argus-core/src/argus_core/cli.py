"""Argus 0.2 中文 CLI：只操作 Schema、状态、审批、锁与 promotion。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (  # pyright: ignore[reportMissingImports]
    Actor,
    Approval,
    ApprovalAction,
    ApprovalStage,
    DelegationGrant,
    Surface,
    Workstream,
)
from .promotion import load_verified_merge_fact, promote  # pyright: ignore[reportMissingImports]
from .store import IterationStore, StoreError  # pyright: ignore[reportMissingImports]


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return parsed.astimezone(UTC)


def _confined_file(project_root: Path, supplied: Path, *, label: str) -> Path:
    root = project_root.resolve()
    candidate = supplied if supplied.is_absolute() else root / supplied
    if "\x00" in str(candidate) or "\\" in str(candidate):
        raise ValueError(f"{label} 不得包含 NUL 字符")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} 必须是项目目录内的普通文件")
    try:
        relative = candidate.relative_to(root)
        if ".." in relative.parts:
            raise ValueError(f"{label} 包含路径穿越")
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"{label} 不得经过符号链接")
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} 必须位于项目目录内且不得经过符号链接") from exc
    return resolved


def _sha256(path: Path, supplied: str | None) -> str:
    if supplied:
        return supplied
    if not path.is_file() or path.is_symlink():
        raise ValueError("artifact-sha256 缺失，且 artifact 不是安全的本地文件")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metadata(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"metadata 必须使用 key=value: {value!r}")
        key, item = value.split("=", 1)
        if not key or not item:
            raise ValueError(f"metadata 不能为空: {value!r}")
        result[key] = item
    return result


def _document_json(document: Any) -> str:
    return json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=argparse.SUPPRESS,
        help="项目根目录",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="argus", description="Argus 0.2 控制面 CLI")
    parser.add_argument("--version", action="version", version="0.2.0")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    iteration = sub.add_parser("iteration", help="迭代控制")
    _add_common(iteration)
    iteration_sub = iteration.add_subparsers(dest="iteration_command", required=True)
    create = iteration_sub.add_parser("create", help="创建 v2 iteration")
    _add_common(create)
    create.add_argument("iteration_id")
    create.add_argument(
        "--surface",
        action="append",
        choices=[item.value for item in Surface],
        required=True,
    )
    create.add_argument("--workstream-id", action="append")
    create.add_argument("--metadata", action="append", default=[])
    status = iteration_sub.add_parser("status", help="读取 iteration")
    _add_common(status)
    status.add_argument("iteration_id")
    validate = iteration_sub.add_parser("validate", help="重新验证 iteration")
    _add_common(validate)
    validate.add_argument("iteration_id")

    init = sub.add_parser("init", help="create 的简写")
    _add_common(init)
    init.add_argument("iteration_id")
    init.add_argument(
        "--surface",
        action="append",
        choices=[item.value for item in Surface],
        required=True,
    )
    init.add_argument("--workstream-id", action="append")
    init.add_argument("--metadata", action="append", default=[])

    approve = sub.add_parser("approve", help="追加审批事实")
    _add_common(approve)
    approve.add_argument("iteration_id")
    approve.add_argument("--workstream-id", required=True)
    approve.add_argument("--stage", choices=[item.value for item in ApprovalStage], required=True)
    approve.add_argument("--action", choices=[item.value for item in ApprovalAction], required=True)
    approve.add_argument("--actor", choices=[item.value for item in Actor], required=True)
    approve.add_argument("--artifact", required=True)
    approve.add_argument("--artifact-sha256")
    approve.add_argument("--approval-id")
    approve.add_argument("--delegation-id")
    approve.add_argument("--note")
    approve.add_argument("--recorded-at")

    transition = sub.add_parser("transition", help="迁移 workstream 状态")
    _add_common(transition)
    transition.add_argument("iteration_id")
    transition.add_argument("--workstream-id", required=True)
    transition.add_argument("--to", required=True)
    transition.add_argument("--actor", choices=[item.value for item in Actor], required=True)
    transition.add_argument("--reason")

    delegation = sub.add_parser("delegation", help="结构化授权")
    _add_common(delegation)
    delegation_sub = delegation.add_subparsers(dest="delegation_command", required=True)
    grant = delegation_sub.add_parser("grant")
    grant.add_argument("iteration_id")
    grant.add_argument("--id", required=True)
    grant.add_argument("--basis")
    grant.add_argument("--basis-file", type=Path)
    grant.add_argument(
        "--scope",
        action="append",
        choices=[item.value for item in ApprovalStage],
        required=True,
    )
    grant.add_argument("--granted-at")
    grant.add_argument("--expires-at", required=True)

    promotion = sub.add_parser("promote", help="写入已核验的 GitHub merge fact")
    _add_common(promotion)
    promotion.add_argument("iteration_id")
    promotion.add_argument("--workstream-id", required=True)
    promotion.add_argument(
        "--fact-file",
        type=Path,
        required=True,
        help="独立 GitHub verifier 产生的 MergeFact envelope（YAML/JSON）",
    )
    return parser


def _create(args: argparse.Namespace, store: IterationStore) -> Any:
    ids = args.workstream_id or [f"{surface}-workstream" for surface in args.surface]
    if len(ids) != len(args.surface):
        raise ValueError("--workstream-id 必须与 --surface 一一对应")
    streams = [
        Workstream(id=item, surface=Surface(surface))
        for item, surface in zip(ids, args.surface, strict=True)
    ]
    document = store.create(args.iteration_id, streams)
    if args.metadata:
        document, _ = store.transact(
            args.iteration_id,
            lambda current: current.metadata.update(_metadata(args.metadata)),
        )
    return document


def _approve(args: argparse.Namespace, store: IterationStore) -> Any:
    document = store.load(args.iteration_id)
    artifact_path = _confined_file(store.project_root, Path(args.artifact), label="artifact")
    artifact_reference = artifact_path.relative_to(store.project_root).as_posix()
    approval = Approval(
        id=args.approval_id or f"approval-{len(document.approvals) + 1:04d}",
        workstream_id=args.workstream_id,
        stage=ApprovalStage(args.stage),
        action=ApprovalAction(args.action),
        actor=Actor(args.actor),
        artifact=artifact_reference,
        artifact_sha256=_sha256(artifact_path, args.artifact_sha256),
        recorded_at=_timestamp(args.recorded_at),
        note=args.note,
        delegation_id=args.delegation_id,
    )
    return store.approve(args.iteration_id, approval)


def _grant(args: argparse.Namespace, store: IterationStore) -> Any:
    if bool(args.basis) == bool(args.basis_file):
        raise ValueError("必须且只能提供 --basis 或 --basis-file")
    basis_file = args.basis_file
    if basis_file is not None:
        basis_file = _confined_file(store.project_root, basis_file, label="basis-file")
    basis = basis_file.read_text(encoding="utf-8") if basis_file else args.basis
    if basis is None:
        raise ValueError("授权 basis 不能为空")
    granted_at = _timestamp(args.granted_at)
    grant = DelegationGrant(
        id=args.id,
        basis=basis,
        basis_sha256=hashlib.sha256(basis.encode("utf-8")).hexdigest(),
        scope=[ApprovalStage(item) for item in args.scope],
        granted_at=granted_at,
        expires_at=_timestamp(args.expires_at),
    )
    return store.grant(args.iteration_id, grant)


def _promote(args: argparse.Namespace, store: IterationStore) -> Any:
    fact_path = _confined_file(store.project_root, args.fact_file, label="fact-file")
    verified = load_verified_merge_fact(fact_path)
    if verified.fact.workstream_id != args.workstream_id:
        raise ValueError("verifier fact workstream_id does not match the target")
    promote(store, args.iteration_id, args.workstream_id, verified)
    return store.load(args.iteration_id)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in {"iteration", "init"}:
            command = args.iteration_command if args.command == "iteration" else "create"
            store = IterationStore(args.root)
            if command == "create":
                document = _create(args, store)
            elif command in {"status", "validate"}:
                document = store.load(args.iteration_id)
            else:  # pragma: no cover - argparse restricts this branch
                raise ValueError(f"未知 iteration 命令: {command}")
        elif args.command == "approve":
            document = _approve(args, IterationStore(args.root))
        elif args.command == "transition":
            document = IterationStore(args.root).transition(
                args.iteration_id,
                args.workstream_id,
                args.to,
                args.actor,
                args.reason,
            )
        elif args.command == "delegation":
            document = _grant(args, IterationStore(args.root))
        elif args.command == "promote":
            document = _promote(args, IterationStore(args.root))
        else:  # pragma: no cover - argparse restricts this branch
            raise ValueError(f"未知命令: {args.command}")
        sys.stdout.write(_document_json(document))
        return 0
    except (OSError, StoreError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
