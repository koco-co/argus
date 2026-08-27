# ADR-011: `accepted` closes the PR; `merged` is finalized after the merge event

- Date: 2026-08-27
- Status: Accepted
- Related: PRD §5, DATA_MODEL §3, Roadmap 9.2–9.3, ADR-001

## Background

Requiring `iteration.yaml.state=merged` inside the merge PR's own DoD is circular: before the GitHub merge the state would be false; writing truthfully afterwards is impossible because the source branch is gone — committing then would need a second PR, whose verification again demands `merged`.

## Decision

The merge-readiness terminal state on the PR branch is `accepted`. After the actual GitHub merge of `test/<iteration-id>` into `release`, `scripts/finalize_merge.py` commits the state update to `merged` directly onto `release`, appending an event carrying the real merge SHA, PR number, and timestamp. Validators treat `accepted` as the required pre-merge terminal state and accept `merged` only with a matching recorded merge event.

## Rationale

Audit history must record facts, not predictions; anchoring `merged` to the real merge event removes both the fabrication pressure and the chicken-and-egg loop.

## Alternatives Considered

| Alternative | Why rejected |
| --- | --- |
| Pre-write `merged` before merging | State lies until the merge happens; cannot bind real SHA/time |
| Merge-status webhook bot with elevated platform permissions | External dependency beyond single-operator v1 scope; script invocation is auditable in-repo |
