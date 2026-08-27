# ADR-001: Single long-lived `release` branch per repo

- Date: confirmed during design phase (exact session date not recorded); consolidated into ADR form on 2026-08-27
- Status: Accepted
- Related: Implementation Guide §Decisions (original wording), PRD §1/§7, Roadmap Phase 9

## Background

Iterations produce test branches (`test/<iteration-id>`) that must merge somewhere stable where regression automation lives. The repo needs a merge target whose protection rules keep acceptance human-controlled.

## Decision & Rationale

One long-lived protected `release` branch per target-app repo; every iteration merges via PR from its `test/<iteration-id>` branch after user acceptance. v1 permits at most one non-terminal iteration per repository, so the branch model and long-lived automation assets do not face concurrent iteration ownership in the initial release. Confirmed originally in Implementation Guide v1.0 with rationale: simple lifecycle matching single-team, serial-iteration usage in v1.

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| `release/<major>` split branches | Premature until a breaking rewrite of the automation layer itself; revisit only if a future iteration requires it | IG v1.0 decision text |

## Impact

Branch protection config becomes a real roadmap task (branch creation/protection was missing from v1.0 task list — added to Roadmap Phase 0). The single-in-progress rule is enforced by iteration validation; parallel multi-iteration work is a post-v1 change requiring a new asset ownership decision (per-module ownership registry / CODEOWNERS-style mapping agreed **before** the single-in-progress rule is lifted — module directories under `automation/` are the natural ownership unit).
