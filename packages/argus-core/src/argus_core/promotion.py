"""从已验收 workstream 到 merged/promoted 的事实收口。"""

from __future__ import annotations

from .approvals import ApprovalError, require_latest  # pyright: ignore[reportMissingImports]
from .models import (  # pyright: ignore[reportMissingImports]
    ApprovalAction,
    ApprovalStage,
    IterationDocument,
    IterationStatus,
    MergeFact,
    WorkstreamStatus,
)
from .store import IterationStore, StoreError  # pyright: ignore[reportMissingImports]


class PromotionError(ValueError):
    """promotion 缺少人工批准、外部事实或覆盖链。"""


def promote(
    store: IterationStore,
    iteration_id: str,
    workstream_id: str,
    fact: MergeFact,
) -> None:
    """只接受已被外部核验的 GitHub merge fact，不自行猜测或伪造 SHA。"""

    def mutate(document: IterationDocument) -> None:
        if document.status == IterationStatus.PROMOTED:
            raise PromotionError("iteration is already promoted")
        if fact.workstream_id != workstream_id:
            raise PromotionError("merge fact workstream_id does not match the target")
        if fact.repository.strip() == "":
            raise PromotionError("merge fact repository must be non-empty")
        try:
            workstream = document.workstream(workstream_id)
        except KeyError as exc:
            raise PromotionError(str(exc)) from exc
        if workstream.status != WorkstreamStatus.PASSED:
            raise PromotionError("only a passed workstream can be promoted")
        try:
            require_latest(
                document,
                workstream_id,
                ApprovalStage.PROMOTION,
                ApprovalAction.APPROVED,
            )
        except ApprovalError as exc:
            raise PromotionError(str(exc)) from exc
        workstream.status = WorkstreamStatus.PROMOTED
        document.promotions.append(fact)
        if all(item.status == WorkstreamStatus.PROMOTED for item in document.workstreams):
            document.status = IterationStatus.PROMOTED
        else:
            # 多 workstream iteration 在最后一条事实到达前保持 active。
            document.status = IterationStatus.ACTIVE

    try:
        store.transact(iteration_id, mutate)
    except (StoreError, ValueError) as exc:
        raise PromotionError(str(exc)) from exc
