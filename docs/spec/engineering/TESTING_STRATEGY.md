# Testing Strategy

How **this framework verifies itself** (scripts, schemas, skills' mechanical gates) — distinct from the regression suites the framework *generates*, whose execution strategy lives in PRD §4.7 and CODING_STANDARDS patch rules.

## Layering & Coverage

| Test layer | Verifies | Boundaries / doubles | Key scenarios | Evidence / plan |
| --- | --- | --- | --- | --- |
| Unit | Pure logic inside scripts: schema registry lookup, statement-head DB verb gate, state-transition legality function, marker consistency rules, staleness hash computation, seed-namespace formatter | No filesystem or network; fixtures inline | Each public behavior of every checker in `scripts/` | planned; Roadmap Phase 1 DoDs require pass+fail fixture per script |
| Integration | One script ↔ its fixture tree: `validate_schema.py` against the checked-in sample iteration; exporters byte-reproducibility (two runs → identical SHA-256); `run_plugin.py` error contract with empty registry; coverage tiers across a crafted partial/complete traceability matrix | Real files under `scripts/tests/fixtures/`, no target app | Every artifact validates/rejects correctly; stale-propagation verdicts; tier escalation | planned; Phase 0–2 DoDs |
| End-to-end (framework) | The generated pipeline itself: one requirement through M1→M9 against the pinned harness; anti-cheat proofs for the self-debug loop | Real target app via `target_app_*` scripts; the loop is session-side agent work observed by transcript + diff review | Phase 9 acceptance pair (UI-led + API-led); three self-debug proof cases: (a) fixable defect reaches green within budget; (b) unfixable stub ends cleanly at budget; (c) product-behavior mismatch escalates and final diff shows zero forbidden-scope touches | planned; Phases 3–6 are human acceptance checkpoints by nature |

Anti-cheat proof case design note: broken-test fixtures must represent realistic generation faults (stale selector, missing wait, wrong model typing), not trivial typos — otherwise passing them proves nothing about real repair capability.

## Coverage Expectations & Completion Conditions

No numeric coverage quota is imposed (an unmeasured "%"; would be decorative). Completion is defined per component instead:

- Every checker script ships with ≥3 positive and ≥3 negative fixtures proving it rejects what it exists to reject (`check_layering.py` forbidden imports, POM violations in both directions, write-verb escapes, secret patterns, marker inconsistencies).
- Every JSON Schema (DATA_MODEL §2–§10) has valid-fixture-passes / invalid-fixture-rejects pairs committed beside it.
- Phase exit criteria double as the framework's own coverage ledger — Roadmap phases carry explicit exit conditions precisely so "covered" stays checkable rather than aspirational.

## Self-Debug & Retry Rules

(Authoritative definitions: PRD §4.7; this section states how compliance is *verified*.)

- Budgets: default 5 debug cycles per invocation; the earlier validation fix-loop budget (3) is separate and named distinctly (`validation_retry` vs `debug_budget`) to prevent conflation.
- Allowed auto-fix classes vs escalate-immediately classes follow the PRD taxonomy table verbatim; classification is recorded per attempt (`failure_class`).
- Early-stop triggers beyond budget: two consecutive attempts producing near-identical diffs (suspected environment/flake cause), or any patch touching frozen scope.
- Post-patch verification battery runs before any re-run; static-gate failure consumes budget and reverts.
- Mid-loop contact must be zero. Verified during dry runs by transcript review (Roadmap 5.5-style checks) and at acceptance by diffing accumulated `attempts[].diff_ref` patches against frozen scope.
- Evidence capture: Allure attachments from failed cycles are redacted at source (no Authorization/Cookie headers or credential-shaped fields — same boundary rules as DATA_MODEL §10); optional video/trace attachment per failed retry aids replay review.
- Rerun granularity: failing subset plus intra-module dependencies only; full-suite reruns happen at terminal states.

## Local Execution

All commands and prerequisites live in [ENVIRONMENT_SETUP.md](./ENVIRONMENT_SETUP.md) (marked defined-vs-executed). Preconditions for anything touching automation suites: pinned harness healthy (`make target-app-healthcheck`), `config/env.local.yaml` filled, seeded data present. Skill dry-run tasks (Roadmap Phases 3–6) are human acceptance checkpoints run inside an agent session, not CI steps; the checked-in hand-written sample iteration lets script-side integration tests run without any LLM involvement.

## Target-App Harness & Seed Policy

Authoritative home of the former Implementation Guide §2 (pinned versions & lifecycle scripts, seeded entities, isolation rules).

**Pinning**: `target-app/medusa.lock.yaml` pins exact backend commit/tag, storefront starter commit, postgres/redis image digests, node version (ADR-002). Five wrapper scripts own one responsibility each, idempotent unless noted:

| Script | Responsibility |
| --- | --- |
| `target_app_up.py` | compose up from lockfile, migrations, wait-for-ready, print base URLs |
| `target_app_seed.py` | seed via Admin API; idempotency keys derived from env name so re-seeding converges |
| `target_app_reset.py` | rebuild containers + re-seed to a known state (between major runs / on escalation) |
| `target_app_healthcheck.py` | probe store+admin until healthy or timeout; non-zero exit otherwise |
| `target_app_down.py` | compose down, optional volume retention |

**Seeded entities (the only sanctioned fixture source)**: region+currency (`usd`) · product with inventory · shipping option · manual/mock payment provider (completes without an external gateway) · test customer · discount code whose expected total is computable at runtime (percentage-based). Generated assertions read expected values from seeded-context fixtures, never hardcoded literals.

**Isolation rules** (binding for generated suites): namespace = `run_id` for emails/codes/names → parallel-safe; seeds idempotent; cleanup best-effort but executed even after failures (`always()` semantics) and only through APIs/container rebuild — never direct DB writes; xdist requires worker-scoped browser/session fixtures, no cross-test context sharing; flake suspicion belongs to failure-class reporting (`environment_unavailable`, near-identical-diff early stop), never silent retries inside test code.

**CI ordering**: `up → migrate+seed → healthcheck → env.ci.yaml from secrets → static prerequisites → pytest → collect artifacts (allure/run-summary/diffs) → notify (always(), continue-on-error) → down` — concrete workflow shape in ARCHITECTURE §8.
