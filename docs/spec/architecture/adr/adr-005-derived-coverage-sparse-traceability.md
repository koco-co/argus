# ADR-005: Traceability rows are sparse; coverage is derived, not hand-maintained

- Date: 2026-08-27
- Status: Accepted (v1.3 exemption storage amendment; replaces v1.0 traceability schema)
- Related: DATA_MODEL §2.1/§8, PRD §4.2/§5.1/M10, Roadmap Phase 1, ADR-009

## Background

v1.0's `traceability.schema.json` required `requirement_id` **and** `test_point_id` on every row while also offering `coverage_status` values like `requirement_only` — states the shape made impossible to represent. It also used a single generic `case_id` that could not distinguish functional from API cases, referenced a `must_automate` flag absent from the requirements schema, and gave three documents three different strictness levels for "coverage".

## Decision & Rationale

1. Rows hold only the fields known so far (`test_point_id`, `functional_case_id`, `api_case_id`, `automation_test_ids[]` all optional); JSON Schema validates *shape*.
2. The hand-written `coverage_status` field is removed. Coverage depth is computed by `check_coverage.py` per PRD §5.1's tiers against each iteration's own stage — eliminating a redundant, drift-prone manual field.
3. Functional and API case links are separate fields.
4. v1.1 originally kept exemption flags on requirement rows. v1.3 supersedes that placement: accepted `requirements.yaml` is immutable, and reasoned exemptions live in the separately validated `exemptions.yaml` contract described by ADR-009.

Rationale: every observed defect in v1.0 came from storing a cached summary of what the row already implies. Derivation removes the update path entirely.

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| Keep `coverage_status` + conditional-required repair (if-then required fields) | Still a second source of truth that can disagree with row contents | Qwen P0-1 proposal; superseded |
| Split into three link tables (R-T, T-C, C-A) | Normalizes away one row = one requirement chain, complicating reads; sparse rows keep it single-file simple | GLM P1-3 alternative |

## Impact

`check_coverage.py` gains referential-integrity + tier modes (Roadmap Phase 1 task updated). Row upsert semantics defined as idempotent replace keyed on the id tuple (Kimi review adoption).
