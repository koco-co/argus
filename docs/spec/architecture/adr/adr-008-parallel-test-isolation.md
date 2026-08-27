# ADR-008: Namespaced Isolation for Parallel Test Execution

- Status: Accepted
- Date: 2026-08-27
- Related: TESTING_STRATEGY.md, PRD §4.7, Roadmap 5.1, ADR-001

## Context

The original project brief defaulted to serial execution and allowed parallel workers to share credentials and test data, relying on execution order to avoid conflicts. The v1.1 engineering contract intentionally moved to run-scoped data namespaces and worker-isolated browser/session fixtures, but the reversal was not recorded as a formal decision.

## Decision

Keep the namespaced, parallel-safe model. Generated identities, codes, and names carry the execution namespace; seeds are idempotent; cleanup is performed through approved APIs or container rebuilds; and each xdist worker receives isolated browser/session fixtures with no cross-test context sharing.

## Rationale

Shared credentials and order-dependent data make failures flaky, difficult to reproduce, and difficult to distinguish from product defects. Explicit namespaces and worker isolation make parallel execution deterministic enough for regression use and align the test data model with pytest-xdist's process model.

## Consequences

- Fixture and seed design is more involved and must be proven in Roadmap 5.1 with a real parallel run.
- Serial execution remains valid for diagnosis, but correctness may not depend on serial ordering.
- The isolation rule is binding for generated suites and is part of the v1 acceptance evidence.
