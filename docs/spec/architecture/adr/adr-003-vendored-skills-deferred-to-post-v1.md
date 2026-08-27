# ADR-003: Cross-repo skill reuse deferred to post-v1 (in-repo `.agents/skills/` for now)

- Date: 2026-08-27
- Status: Accepted (supersedes Implementation Guide v1.0 Decision 1)
- Related: PRD §1 scope, Architecture §2, Roadmap Phase 9 gate

## Background

Implementation Guide v1.0 "decided" a separate `skills-template` upstream repo with `scripts/sync_skills.py` diff-PR syncing, while the PRD scoped v1 to a single repo and the Roadmap contained no task for either the template repo or the sync script — a decision made outside its task plan.

## Decision & Rationale

v1 keeps skills **vendored in-repo** under `.agents/skills/` of each target-app repo; no upstream repo, no sync tooling in v1. The template-repo idea is recorded as the post-v1 extraction step once at least two target repos exist and real divergence patterns are known. Rationale: premature infrastructure with zero tasks; single-repo v1 removes an entire failure class (silent drift, conflict resolution) from the critical path. `single repo` in the PRD means *the runtime repo per target app*; nothing about it forbids later extracting shared skills.

## Considered Alternatives

| Alternative | Why not chosen (this round) | Basis |
| --- | --- | --- |
| Git submodule live-link | v1.0 already rejected: silent drift on every clone | IG v1.0 |
| Vendoring + sync script now | No second consumer repo exists yet; complexity before need | review consensus (Qwen P1-3, Grok, GLM) |

## Impact

Roadmap gains an explicit post-v1 deferral line instead of an orphaned commitment. If multi-repo adoption arrives early, extract then; skills carry `version:` frontmatter from the start so future sync can diff meaningfully.
