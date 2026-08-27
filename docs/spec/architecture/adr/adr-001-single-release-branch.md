# ADR-001: Single long-lived `release` branch per repo

- Date: confirmed during design phase (exact session date not recorded); consolidated into ADR form on 2026-08-27
- Status: Accepted
- Related: Implementation Guide §Decisions (original wording), PRD §1/§7, Roadmap Phase 9

## Background

Iterations produce test branches (`test/<iteration-id>`) that must merge somewhere stable where regression automation lives. The repo needs a merge target whose protection rules keep acceptance human-controlled.

## Decision & Rationale

One long-lived protected `release` branch per target-app repo; every iteration merges via PR from its `test/<iteration-id>` branch after user acceptance. Confirmed originally in Implementation Guide v1.0 with rationale: simple lifecycle matching single-team, serial-iteration usage in v1.

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| `release/<major>` split branches | Premature until a breaking rewrite of the automation layer itself; revisit only if a future iteration requires it | IG v1.0 decision text |

## Impact

Branch protection config becomes a real roadmap task (branch creation/protection was missing from v1.0 task list — added to Roadmap Phase 0). Parallel multi-iteration merges could contend on one branch; accepted limitation tracked in RISKS_AND_KNOWN_ISSUES.
