# ADR-009: Exemptions are separate and accepted artifacts reopen explicitly

- Date: 2026-08-27
- Status: Accepted
- Related: DATA_MODEL §2/§2.1/§8, PRD §4.2/§5/§6, Roadmap 1.15b

## Background

The v1.1 requirement schema stored `testable` and `automation_required` flags on the same YAML that becomes accepted and hash-audited. M2 then had to either mutate an accepted artifact or leave an exemption without a stable home. Both choices weakened auditability and made R→T coverage ambiguous.

## Decision & Rationale

1. `requirements.yaml` contains only clarified requirement facts and becomes read-only after M1 acceptance.
2. M2 writes `exemptions.yaml`, where each requirement may have at most one reasoned `not_testable` or `manual_only` exemption.
3. A user-triggered change to any accepted upstream artifact goes through `scripts/reopen_iteration.py`; it preserves allocated IDs, records the event, marks downstream artifacts stale, and blocks stale consumers until regeneration or explicit re-confirmation.
4. `scripts/record_approval.py` is the only approval writer. Agents must wait for explicit user acceptance and may not hand-edit `approvals[]`。`exemptions.yaml` 使用独立的 `stage=exemptions, action=accepted` 记录；UI 分支还需独立的 `test_points` 批准，API 分支在进入 `requirements_mapped` 前也必须具备该豁免批准。

This keeps the accepted source immutable while making every exception and reopen auditable, branch-aware, and mechanically checkable.

## Impact

Coverage checks consume `exemptions.yaml`; UI iterations require R→T unless a reasoned exemption exists, while API iterations use R→A through `api_cases.requirement_ids[]`. The former requirement-level flags are removed from the authoritative schema.
