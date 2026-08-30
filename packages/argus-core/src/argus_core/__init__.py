"""Argus 0.2 control-plane package.

This package owns contracts and promotion state only. It intentionally does not
assemble prompts, call models, execute Skills, or provide an Agent Runtime.
"""

from .approvals import (  # pyright: ignore[reportMissingImports]
    ApprovalError,
    append_approval,
    latest_approval,
    require_latest,
    verify_delegation,
)
from .models import (  # pyright: ignore[reportMissingImports]
    SCHEMA_VERSION,
    Actor,
    Approval,
    ApprovalAction,
    ApprovalStage,
    DelegationGrant,
    IterationDocument,
    IterationStatus,
    LifecycleEvent,
    MergeFact,
    Surface,
    Workstream,
    WorkstreamStatus,
)
from .parsing import ParseError, load_json, load_yaml  # pyright: ignore[reportMissingImports]
from .promotion import (  # pyright: ignore[reportMissingImports]
    PromotionError,
    VerifiedMergeFact,
    load_verified_merge_fact,
    promote,
)
from .schema import iteration_schema, validate_iteration  # pyright: ignore[reportMissingImports]
from .state import StateError, transition  # pyright: ignore[reportMissingImports]
from .store import IterationStore, StoreError  # pyright: ignore[reportMissingImports]

__version__ = "0.2.0"

__all__ = [
    "Actor",
    "Approval",
    "ApprovalAction",
    "ApprovalError",
    "ApprovalStage",
    "ParseError",
    "DelegationGrant",
    "IterationDocument",
    "IterationStatus",
    "IterationStore",
    "LifecycleEvent",
    "MergeFact",
    "PromotionError",
    "VerifiedMergeFact",
    "load_verified_merge_fact",
    "StateError",
    "StoreError",
    "SCHEMA_VERSION",
    "Surface",
    "Workstream",
    "WorkstreamStatus",
    "append_approval",
    "latest_approval",
    "promote",
    "require_latest",
    "iteration_schema",
    "load_json",
    "load_yaml",
    "validate_iteration",
    "transition",
    "verify_delegation",
]
