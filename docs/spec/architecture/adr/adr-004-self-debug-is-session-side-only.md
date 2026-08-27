# ADR-004: Self-debug loop is session-side only; CI never patches tests

- Date: 2026-08-27
- Status: Accepted (resolves v1.0 contradiction between Makefile entry and skill definition)
- Status context: multiple independent reviews flagged that v1.0's `-m agents.self_debug_runner` referenced a nonexistent Python package while the same artifact was also defined as an agent-driven skill
- Related: PRD §4.7, Architecture §2 (`scripts/self_debug_helper.py`), Roadmap Phase 5, CODING_STANDARDS §patch rules

## Background

M9's fix-and-rerun loop needs a runtime. Two viable shapes: (A) an in-session agent-driven skill following SKILL.md; (B) a standalone Python orchestrator calling an LLM API. v1.0 implied both: the Roadmap defined only the skill, while the Makefile invoked an undefined module.

## Decision & Rationale

**Shape A for v1**: the self-debug loop runs inside the coding-agent session, driven by `self-debug-runner/SKILL.md`, using `scripts/self_debug_helper.py` purely for mechanical bookkeeping (budget count, attempt log entries, diff capture). CI executes committed tests read-only and never modifies code. Rationale:

1. Session-side execution matches M9's interaction contract (contact user only at terminal states) without new infrastructure.
2. Industry practice converges on self-healing producing *reviewable changes offline*, never auto-patching inside deployment-gating pipelines.
3. Shape B requires model credentials/budget/sandbox governance that v1 explicitly does not want to build; if ever needed it becomes a separate orchestrated service with its own ADR.

Makefile consequence: no `debug` target invoking a phantom package; debugging is documented as the agent-session flow.

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| Python orchestrator + LLM API (CI-capable self-debug) | Cost/budget/sandbox governance out of v1 scope; duplicates the agent harness | review analysis |
| CI-invoked patch loop behind flag | Violates "CI fixes produce PRs for review" practice; muddies audit trail | Currents/QA-practice guidance |

## Impact

`run-summary.yaml` diff history becomes the human-review artifact at acceptance; Roadmap Phase 7's regression pipeline defines no self-debug stage (static-checks + e2e execute committed tests only).
