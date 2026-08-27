# ADR-007: Repository layout redesign (v1 scattered split → consolidated v2)

- Date: confirmed during design phase (exact session date not recorded); consolidated on 2026-08-27
- Status: Accepted
- Related: ARCHITECTURE §2/§9, DATA_MODEL intro, original source document "Repo structure v2 proposal" (merged into this spec set on 2026-08-27 and deleted)

## Background

The v1 draft scattered an iteration's artifacts across `requirements/`, `testcases/*/`, and `artifacts/`, keyed automation under `<iteration-id>`, and distributed pipeline knowledge across nine granular skills. Three structural problems followed: duplicated data (nothing single-source), automation code going stale whenever its owning iteration aged, and rule drift because one phase's prompt/schema lived in three skills.

## Decision & Rationale

Four coupled choices, recorded here because their original write-up lives in a deleted document:

1. **Skills consolidated 9 → 6 by business capability** (`test-design`, `api-test-design`, `web-automation-generation`, `api-automation-generation`, `self-debug-runner`, `skill-self-optimizer`): grouped by phase-of-work so a schema or prompt-rule change touches one SKILL.md, not three.
2. **`plugins/` placeholder layer**: requirement/design/API source ingestion separated from test-design logic — plugins fetch+normalize, skills consume normalized payloads (deepened later by ADR-006).
3. **`iterations/<id>/` consolidation**: exactly one directory holds every formal artifact of an iteration; nothing duplicated elsewhere.
4. **`automation/` keyed by business module**, independent of iteration lifecycle; iterations link out via `traceability.yaml` only. Iteration directories are write-once records keyed by time; `automation/` is continuously edited regression capital keyed by module. This coupling-severing is the structural heart of v2.
5. Every pipeline stage gained a **structured YAML source of truth validated against a schema** (expanded to the full contract set in DATA_MODEL); human-readable `.md`/`.xmind`/`.xlsx` are always derived, never hand-edited, never LLM freeform output.
6. `knowledge/` stays deliberately flat for v1 (revisit trigger pre-agreed in RISKS_AND_KNOWN_ISSUES #9).

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| Keep iteration-keyed automation tree | Tests expire when iterations close; no long-lived regression asset | v1 review discussion |
| One skill per pipeline step | Rule/schema duplication across SKILL.mds caused observed drift | v1 review discussion |

## Impact

Layout codified as canonical in ARCHITECTURE §2 and scaffolded by Roadmap Phase 0 tasks; fixture-tree DoD enforces exact conformance. Config/env handling, POM conventions, guardrail scripts referenced there were inherited unchanged.
