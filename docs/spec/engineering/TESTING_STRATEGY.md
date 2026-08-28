# Testing Strategy

How **this framework verifies itself** (scripts, schemas, skills' mechanical gates) — distinct from the regression suites the framework *generates*, whose execution strategy lives in PRD §4.7 and CODING_STANDARDS patch rules.

## Layering & Coverage

| Test layer | Verifies | Boundaries / doubles | Key scenarios | Evidence / plan |
| --- | --- | --- | --- | --- |
| Unit | Pure logic inside scripts: schema registry lookup, statement-head DB verb gate, state-transition legality function, marker consistency rules, staleness hash computation, seed-namespace formatter | No filesystem or network; fixtures inline | Each public behavior of every checker in `scripts/` | 已实现；2026-08-28 全量框架测试 403 项通过 |
| Integration | One script ↔ its fixture tree: `validate_schema.py` against the checked-in sample iteration; extraction and parsing of every JSON block in DATA_MODEL; exporters byte-reproducibility (two runs → identical SHA-256) plus semantic export shape; `run_plugin.py` error contract with empty registry; coverage tiers across crafted UI/API partial/complete traceability matrices; approval/reopen and source-payload validation | Real files under `scripts/tests/fixtures/`, no target app | Every artifact validates/rejects correctly; every documented schema parses; stale-propagation and reopen verdicts; branch-aware tier escalation; approval provenance; export structure | 已实现；真实 CLI、目录输入、跨秒 XLSX 与 UI/API nodeid 反向闭包均有回归测试 |
| End-to-end (framework) | The generated pipeline itself: one requirement through M1→M9 against the pinned harness; anti-cheat proofs for the self-debug loop | Real target app via `target_app_*` scripts; the loop is session-side agent work observed by transcript + diff review | Phase 9 acceptance pair (UI-led + API-led); four self-debug proof cases: (a) fixable defect reaches green within budget; (b) unfixable stub ends cleanly at budget; (c) product-behavior mismatch escalates and final diff shows zero forbidden-scope touches; (d) stub-return constant injection is caught by the literal-return heuristic, never silently green | 机器样例已实现并真实运行；正式 Phase 9 仍受用户 approval、外部通知与受保护分支人工合并门禁约束 |

Anti-cheat proof case design note: broken-test fixtures must represent realistic generation faults (stale selector, missing wait, wrong model typing), not trivial typos — otherwise passing them proves nothing about real repair capability.

## Coverage Expectations & Completion Conditions

No numeric coverage quota is imposed (an unmeasured "%"; would be decorative). Completion is defined per component instead:

- Every checker script ships with ≥3 positive and ≥3 negative fixtures proving it rejects what it exists to reject (`check_layering.py` forbidden imports, POM violations in both directions, write-verb escapes, secret patterns, marker inconsistencies, and self-debug patch-scope violations).
- Every JSON Schema (DATA_MODEL §2, §2.1, and §3–§10) has valid-fixture-passes / invalid-fixture-rejects pairs committed beside it.
- Phase exit criteria double as the framework's own coverage ledger — Roadmap phases carry explicit exit conditions precisely so "covered" stays checkable rather than aspirational.

## Self-Debug & Retry Rules

(Authoritative definitions: PRD §4.7; this section states how compliance is *verified*.)

- Budgets: default 5 debug cycles per invocation; the earlier validation fix-loop budget (3) is separate and named distinctly (`validation_retry` vs `debug_budget`) to prevent conflation.
- `classify_failure.py` mechanically pre-classifies pytest evidence; assertions, 5xx, auth and product-behavior mismatches are escalation-only. The LLM may refine only locator-vs-timing within the repairable boundary; classification is recorded per attempt (`failure_class`). **Decision tree (mechanical, fixture-tested)**: TimeoutError with the element absent from the DOM snapshot ⇒ `locator_drift` or `timing` (refinable); element **present** but text/attribute/state differs from expected ⇒ `product_behavior_mismatch` (escalation-only — "fixing" the selector here would mask a real behavior change); network response 5xx ⇒ `backend_5xx`; auth rejection/redirect-to-login ⇒ `auth_failure`; connection refused / container unhealthy ⇒ `environment_unavailable`; assertion failure with element present and matching ⇒ genuine assertion failure, escalation-only.
- Early-stop triggers beyond budget: two consecutive attempts producing near-identical diffs (suspected environment/flake cause), or any patch touching frozen scope.
- One debug cycle is one failing-subset execution, at most one allowed patch, the static verification battery, and one affected-module regression. `check_patch_scope.py` hard-blocks frozen paths, assertions/expected values, seeded expectation formulas, and banned patterns; static-gate failure consumes budget and reverts.
- Affected-module regression means the complete test directory of every business module in the AST import closure of changed project modules; it is run after the failing subset checks and before the next retry.
- Mid-loop contact must be zero. Verified during dry runs by transcript review (Roadmap 5.5-style checks) and at acceptance by diffing accumulated `attempts[].diff_ref` patches against frozen scope.
- Evidence capture: every failed cycle keeps its **Playwright trace** (mandatory — viewer exposes action timeline, DOM snapshots, network) plus redacted console/network log excerpts in the run's directory until acceptance review (no Authorization/Cookie headers or credential-shaped fields — same boundary rules as DATA_MODEL §10); optional video attachment per failed retry aids replay review.
- Rerun granularity: failing subset plus intra-module dependencies only; cases declaring `side_effect: creates|deletes` are excluded from automatic reruns (duplicate-resource risk) unless a reset precedes them; full-suite reruns happen at terminal states.

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

**Seeded entities (the only sanctioned fixture source)**: region+currency (`usd`) · product with inventory · shipping option · manual/mock payment provider (completes without an external gateway) · test customer · discount code whose expected total is computable at runtime (percentage-based). Generated assertions read expected values from seeded-context fixtures, never hardcoded literals. Seed formulas and fixture `expected_*` values are frozen during self-debug; `data_issue` repairs may only change reseed-hook wiring or namespace arguments. Seed integrity is *provable*: the 5.0.2 DoD includes a canary proving that corrupting one seeded value flips a dependent assertion red — guarding against oracle-blind suites that would pass even if seeding broke.

**Isolation rules** (binding for generated suites): namespace = `run_id` for emails/codes/names → parallel-safe; seeds idempotent; cleanup best-effort but executed even after failures (`always()` semantics) and only through APIs/container rebuild — never direct DB writes; xdist requires worker-scoped browser/session fixtures, no cross-test context sharing; flake suspicion belongs to failure-class reporting (`environment_unavailable`, near-identical-diff early stop), never silent retries inside test code. The model and its reversal from shared, order-dependent data are recorded in [ADR-008](../architecture/adr/adr-008-parallel-test-isolation.md).

Roadmap 5.1 must demonstrate the isolation contract with a real parallel run of the same module under at least two workers, repeated sufficiently to expose shared-state contamination; a green serial run alone is not evidence of parallel safety.

The target-app harness is provisioned through Compose as the single source of truth. CI must not also start duplicate native database or cache service containers for the same run.

**CI ordering**: `up → migrate+seed → healthcheck → env.ci.yaml from secrets → static checks → pytest → record-ci summary → collect artifacts (allure/run-summary/diffs) → notify every job (always(), continue-on-error) → down` — concrete workflow shape and trigger matrix in ARCHITECTURE §8. `record-ci` 与摘要通知都以本次 JUnit 存在为前提；此前失败没有 JUnit 时发送当前 job 状态，不能回退到旧摘要。A failed e2e job re-runs **once**; a retry-pass is classified `flaky-suspect` in the notification (never green, never merge-blocking alone; repeated offenders go through the M12 knowledge channel). 手工调度的 `force_failure` 与 `force_flaky` 仅用于重复验收上述失败路径，常规 PR/定时运行固定为 `normal`。A weekly scheduled run executes the full suite against `release` HEAD to catch non-PR drift (image digests, runner/browser upgrades, lockfile drift). GitHub Actions is authoritative for v1; Jenkins is not an acceptance path.
