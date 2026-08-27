# ADR-010: Execution evidence persists per run under `iterations/<id>/runs/<run_id>/`

- Date: 2026-08-27
- Status: Accepted
- Related: DATA_MODEL §9, PRD §2.1/§4.7/M11, ARCHITECTURE §2/§8, Roadmap 5.3/7.1

## Background

The data model declared N runs per iteration (retry cycles, module-scoped invocations, CI vs local), but v1.3 gave each iteration a single `run-summary.yaml` plus one global `reports/allure-results/`. Overwriting semantics made "full attempt diff history" and per-`run_id` replay impossible: a second run clobbered the first, concurrent or interleaved runs mixed results in one Allure directory, and CI could not upload stable evidence for a specific execution.

## Decision

Each M9 invocation creates its own directory `iterations/<id>/runs/<run_id>/` containing that run's `run-summary.yaml`, allure-results/, logs/, and attempt patch references. `run_id` is unique per execution within the iteration (GLOSSARY), so directory creation is atomic — collisions fail loudly instead of overwriting. Global `reports/` remains a gitignored scratch/display area; it is never the fact source. CI archives and uploads run directories. The self-debug helper script acts as evidence recorder for all writes into `runs/` (they are bookkeeping, not patches).

## Rationale

Run evidence is audit input for acceptance ("review every cycle's diffs") and for post-mortems; it must be append-only at execution granularity exactly like the other iteration artifacts are append-only at event granularity.

## Consequences

Slightly larger iteration trees; validators must type-check files per run directory shape rather than one fixed path; notify/export tooling resolves "the latest summary" by newest `run_id` directory rather than a shared filename.
