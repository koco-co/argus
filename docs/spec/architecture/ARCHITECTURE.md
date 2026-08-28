# Architecture Design Document

## AI-Driven Automation Framework

Version: 1.6 · Performance/load testing is reserved for post-v1 · Companion docs: PRD, DATA_MODEL.md, CODING_STANDARDS.md, GLOSSARY.md

> Machine contracts (JSON Schemas) are defined authoritatively in [DATA_MODEL.md](./DATA_MODEL.md); this document owns layering, directory structure, and dependency rules.

---

## 1. Layered Architecture Overview

```
┌───────────────────────────────────────────────────────────────────┐
│  Plugin Interface Layer            plugins/                        │
│  fetch(source_ref) -> normalized SOURCE PAYLOAD envelope.           │
│  run_plugin.py persists the envelope to disk BEFORE validation      │
│  against *_source_payload.schema.json. No case-design logic.        │
│  No LLM calls inside a plugin.                                      │
└───────────────────────────────────────────────────────────────────┘
                              │ persisted source-payload YAML
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Skill Driving Layer                .agents/skills/                │
│  Markdown instruction packages (no importable Python). Convert      │
│  source payloads into internal workflow YAMLs; generate automation  │
│  code only from schema-valid case data (HAR paths route through     │
│  M4/M5 normalization first — PRD §3 M7). Skills invoke plugins      │
│  ONLY via scripts/run_plugin.py (process rule, §3).                 │
└───────────────────────────────────────────────────────────────────┘
                              │ schema-valid internal YAML only
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Data Schema Validation Layer       skills' schemas/ +              │
│                                     scripts/schemas/ +              │
│                                     scripts/schema_registry.yaml    │
│  validate_schema.py = single implementation; called by skills,      │
│  pre-commit, CI. Explicit filename↔schema registry — never          │
│  filename-similarity inference.                                     │
└───────────────────────────────────────────────────────────────────┘
                              │ generates code into ↓
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Long-Term Automation Asset Layer   automation/                     │
│  Organized by business module, independent of iteration lifecycle.  │
│  Linked back to iterations/ only through traceability.yaml row ids; │
│  never reads iteration YAML at test runtime (tests read their own   │
│  pytest.mark metadata).                                             │
└───────────────────────────────────────────────────────────────────┘
```

**Two distinct rule families** (v1.0 conflated them):

- **Data-flow direction** (arrows above): how information moves between layers.
- **Dependency rules** (§3 table): what each *Python-code* directory may import. These apply to real code only (`plugins/`, `scripts/`, `shared/`, `automation/`); `.agents/skills/` is Markdown and cannot be import-scanned — its boundary rules are process rules verified by review plus a lightweight grep check that skills never name direct platform-SDK usage outside `run_plugin.py` invocation.

**Control plane (what sequences the modules?)**: v1 deliberately ships no orchestrator service or skill. The enforced sequence *is* the contract above plus deterministic validators: `iteration.yaml` state transitions are checked by `validate_iteration.py`, tier gates order M-gate progression, and AGENTS.md instructs the agent through confirmation points. An LLM-composed pipeline can therefore only be rejected as invalid after the fact of a step, but every illegal step is caught before it persists. A deterministic orchestrator CLI remains a post-v1 evaluation item (RISKS_AND_KNOWN_ISSUES).

---

## 2. Complete Directory Structure

Canonical target layout for a `<target-app>-automation` repo (Roadmap Phase 0 scaffolds exactly this; additions vs v1.0 flagged ⭐):

```
<target-app>-automation/
├── AGENTS.md                        # ⭐ single source of operating rules (Phase plan: Roadmap 0.6)
├── CLAUDE.md                        # `@AGENTS.md` include only
├── README.md
├── .agents/skills/                  # canonical: functional-test-design, api-test-design,
│   │                                # web-automation-generation, api-automation-generation,
│   │                                # self-debug-runner, skill-self-optimizer
│   │                                # each: SKILL.md + schemas/ + examples/
│   └── <skill>/versions/            # ⭐ prior SKILL.md snapshots kept by optimizer (Roadmap 8.2)
├── .claude/skills/                  # one symlink per skill → .agents/skills/<name>
├── plugins/
│   ├── README.md
│   ├── registry.yaml
│   ├── _interface/
│   │   ├── contract.md
│   │   └── schemas/                 # ⭐ requirement_source_payload.schema.json,
│   │                                #    api_source_payload.schema.json (DATA_MODEL §10)
│   ├── requirement-sources/         # placeholder
│   └── api-sources/                 # placeholder
├── config/
│   ├── env.example.yaml             # committed placeholder shape (incl. read-only-role comment)
│   ├── env.local.yaml               # gitignored
│   ├── env.test.yaml                # gitignored
│   ├── env.prod.yaml                # gitignored (read-only-marked tests only)
│   ├── env.ci.yaml                  # ⭐ generated by CI from repository secrets; never committed
│   ├── notify.example.yaml          # ⭐ committed; notify.yaml remains gitignored
│   └── notify.yaml                  # gitignored
├── iterations/<iteration-id>/
│   ├── iteration.yaml               # ⭐ global state + approvals/events/source_manifest (DATA_MODEL §3)
│   ├── 00-raw/                      # text inputs tracked w/ secret scan; binaries/large ignored,
│   │                                # recorded instead in iteration.yaml.source_manifest[]
│   ├── requirements.yaml / requirement.md  # accepted requirements are immutable
│   ├── exemptions.yaml                     # reasoned exceptions (M2 on UI-led; M4 mapping sub-stage on API-led)
│   ├── test_points.yaml / test_points.md
│   ├── functional-cases.yaml
│   ├── api/spec.normalized.yaml, api/cases.yaml
│   ├── exports/*.xmind, exports/*.xlsx
│   ├── traceability.yaml
│   └── runs/<run-id>/               # ⭐ per-run evidence dir (ADR-010/012): run-summary.yaml +
│                                    #    patch refs committed; allure-results/, logs/, traces/
│                                    #    gitignored — append-only, never overwritten by later runs
├── target-app/                      # ⭐ pinned harness home (ADR-002; policy in TESTING_STRATEGY):
│                                    #    medusa.lock.yaml, compose.yaml, overrides/
├── automation/
│   ├── web/{pages,components,fixtures,tests}/<module>/, web/conftest.py
│   ├── mobile/{android,ios,screens,tests}/<module>/, mobile/conftest.py
│   ├── miniprogram/{pages,tests}/<module>/, miniprogram/conftest.py
│   ├── api/{clients,models,tests}/<module>/, api/har/ (gitignored), api/conftest.py
│   ├── perf/{locustfiles,scenarios}/<module>/
│   └── conftest.py                  # ⭐ root conftest: TEST_ENV=prod read-only collection gate,
│                                    #    marker registration (--strict-markers)
├── shared/
│   ├── utils/
│   ├── assertions/
│   ├── config/settings.py           # ⭐ now part of the canonical tree (was undeclared in v1.0);
│   │                                #    `check` mode validates env files before the M8 approval
│   ├── db/readonly_client.py        # sole sanctioned DB access path (§6)
│   ├── notify/{base,dispatcher}.py  # adapters dingtalk/feishu/wecom/email + dispatcher
│   └── testdata/                    # ⭐ seeding/cleanup hooks per environment (PRD M8/M9 data_issue;
│                                    #    seed-registry.yaml + policy: TESTING_STRATEGY harness section)
├── reports/{allure-results,allure-report}/   # gitignored content, tracked .gitkeep
├── knowledge/{patterns.md,anti-patterns.md,optimization-candidates.yaml,target-app-notes/<target-app>.md}
│                                    # optimization-candidates.yaml: [{skill_name, failure_pattern,
│                                    #   occurrence_count, affected_iterations[], evidence_refs[]}] —
│                                    # M12-updated candidate feed for the skill optimizer (Roadmap 8.2)
├── scripts/
│   ├── new_iteration.py             # scaffolds iterations/<id>/ incl. iteration.yaml
│   ├── schema_registry.yaml         # ⭐ explicit artifact-path ↔ schema binding
│   ├── schemas/                     # ⭐ exemptions / iteration / traceability / run_summary schemas (DATA_MODEL §2.1,3,8,9)
│   ├── validate_schema.py
│   ├── validate_iteration.py        # ⭐ state-transition legality + staleness (hash chain) checks
│   ├── render_md.py
│   ├── export_xmind.py
│   ├── export_xlsx.py
│   ├── check_coverage.py            # branch-aware coverage gate (PRD §5.1)
│   ├── check_functional_expectations.py # expected_kind/seed-rule guard
│   ├── check_api_coverage.py        # ⭐ endpoint happy/negative coverage
│   ├── check_db_readonly.py
│   ├── check_pom_boundary.py        # selectors-in-tests + assertions-in-pages
│   ├── check_api_models.py          # ⭐ client methods ↔ pydantic models + spec fields
│   ├── check_test_markers.py        # ⭐ module/case_id/iteration markers present & consistent
│   ├── check_layering.py
│   ├── check_secrets.py             # ⭐ credential-pattern scan over trackable text
│   ├── check_patch_scope.py          # ⭐ self-debug frozen-scope and banned-pattern guard
│   ├── classify_failure.py           # M9 结构化证据机械预分类（升级类不可降级）
│   ├── self_debug_helper.py          # ⭐ run 摘要、预算、检查点、patch 门禁、AST 受影响模块与 CI 证据
│   ├── record_approval.py            # sole approval writer; requires explicit user action
│   ├── record_event.py               # ⭐ sole writer of `state` transitions + `events[]` (PRD §6)
│   ├── reopen_iteration.py           # user-triggered reopen + stale propagation
│   ├── finalize_merge.py             # ⭐ post-merge `merged` finalization with real merge SHA (ADR-011)
│   ├── check_prod_scope.py           # ⭐ static write-call audit of read_only-marked tests (PRD §6)
│   ├── check_orphan_tests.py         # ⭐ reverse closure: collected nodeids must resolve to cases + trace
│   ├── run_plugin.py
│   ├── _target_app.py               # ⭐ 靶应用锁定配置、Compose 调用与健康/只读角色探测
│   ├── notify.py                    # ⭐ CLI wrapper around shared/notify/dispatcher.py
│   ├── weekly_escalation.py          # 周回归连续失败时创建或复用 GitHub issue
│   ├── target_app_up.py / target_app_seed.py / target_app_reset.py / target_app_healthcheck.py / target_app_canary.py / target_app_down.py   # ⭐ pinned harness (ADR-002; policy in TESTING_STRATEGY)
│   └── tests/                       # ⭐ pytest suites + fixtures validating all scripts above
│       └── fixtures/                # incl. a checked-in hand-written sample iteration
├── .github/workflows/{ci.yml,regression.yml}
├── pyproject.toml, uv.lock, .python-version
├── .pre-commit-config.yaml, Makefile, .gitignore
└── docs/                            # development documentation set (see AGENT_BRIEF index)
```

Gitignore rules resolve the v1.0 conflict between "reports/ ignored" and ".gitkeep committed": ignore directory *contents*, re-include keepers — `reports/**`, `!reports/**/.gitkeep`; same pattern for `automation/api/har/`. Per ADR-012, `iterations/*/runs/*/` tracks only `run-summary.yaml` and patch files; `allure-results/`, `logs/`, and `traces/` beneath a run directory are ignored.

**This tree is the single structural authority**: Roadmap 0.8's structural-diff DoD and every TESTING_STRATEGY/ROADMAP reference to script or directory names defer to it; naming drift found in reviews is fixed here first.

**Future split boundary** (post-v1, RISKS #14): if a second target project materializes, the candidate `argus-core` package is `scripts/` + `scripts/schemas/` + `shared/` (minus target-app seed registries) + `.agents/skills/` templates + the root conftest contract; the per-project adapter keeps `config/`, `target-app/`, seed registries, `knowledge/`, and all generated `automation/`. Marking this now avoids an archaeology exercise at split time.

---

## 3. Module Decoupling Rules

|Directory|May depend on|Must NOT depend on|Enforcement|
|---|---|---|---|
|`plugins/`|stdlib, `httpx`, target-platform SDKs|`.agents/skills/` internals, `automation/`, `iterations/`|import scan (`check_layering.py`)|
|`scripts/`|`plugins/` (loader), `shared/`, schemas, `iterations/` files as **data**|direct platform SDKs beyond loading registered plugins|import scan + path-read lint on `automation` writing side|
|`shared/`|stdlib, declared deps (`httpx`, `pydantic`, `yaml`)|`iterations/**` at runtime, `scripts/`, `plugins/`, `.agents/skills/`|import scan|
|`automation/`|`shared/`, pytest stack, playwright/appium/httpx|`iterations/**` (import OR path-open at test time), `.agents/skills/`, `scripts/`|import scan + AST/path-open scan in CI|
|Skills (Markdown)|— as process rules —|direct platform calls (only via `run_plugin.py`); editing other skills (except optimizer after confirmation)|review + grep check in CI|

Corrections vs v1.0: the prose arrows "`plugins/` → `skills`" described **data flow**, while the table forbade skills-side direct plugin imports — both statements were right but indistinguishable; they are now explicitly separated (§1). The scanner targets Python directories only; "skills call scripts" stays a documented process constraint because there is nothing to import-scan. Honest limit noted: import scanning cannot catch every runtime path-read of iteration YAML by devious means; the check covers AST-level `open()`/`Path()` literals referencing `iterations/` inside `automation/` and accepts residual risk (tracked in RISKS_AND_KNOWN_ISSUES).

---

## 4. Data Contracts

All artifact schemas, the registry binding, and semantic-check ownership live in [DATA_MODEL.md](./DATA_MODEL.md) (single authority — v1.0's "as previously specified" dangling reference is retired).

---

## 5. Code Conventions for Generated Assets

POM structure/rules (page objects carry locators+actions only; tests carry assertions only; selector-free test files; reuse-before-create) and API-client conventions (every method ↔ typed pydantic models, no raw dicts) are specified in [CODING_STANDARDS](../engineering/CODING_STANDARDS.md) with examples. Mechanical enforcement summary here:

|Rule|Checker|Scope|
|---|---|---|
|No locator call inside `*/tests/` (`get_by_*`, `locator(`, `page.click(".sel")`, `page.fill("#id",…)`, XPath helpers)|`check_pom_boundary.py` (AST + call-pattern scan)|`automation/{web,miniprogram,mobile}/tests/**`|
|No `assert`/`expect` inside page/component/screen objects|same script, mirrored rule|`**/{pages,components,screens}/**`|
|Markers present & consistent with path/module tag|`check_test_markers.py`|all generated tests|
|API clients dict-free, model-linked, and fields are a subset of normalized source schemas|`check_api_models.py`|`automation/api/{clients,models,tests}/**`|

---

### 5.1 Automation Asset Ownership & Lifecycle

`automation/` is long-lived and shared across iterations. Generated test filenames are `test_<iteration_id>_<case_id>_<behavior>.py`, so the cross-iteration identity pair prevents file collisions even though `case_id` is only unique within an iteration. A page/component/client method already referenced by another iteration may be extended or have its locator/wait/type corrected, but cannot be deleted without a `retires_nodeids[]` record and a coverage validation showing that no active iteration still depends on it. v1 permits at most one non-terminal iteration per repository; `new_iteration.py` rejects a second in-progress iteration. Retired nodeids remain in traceability history but do not count as active automation coverage.

## 6. DB Read-Only Assertion Interception

Three independent layers, so a single mistake can't cause a write. **The authoritative control is Layer 1** — the regex/wrapper layers are defense-in-depth, never treated as the security boundary (stakeholder decision retained; rationale: SQL syntax evasion makes static matching incomplete — see RISKS_AND_KNOWN_ISSUES).

**Layer 1 — DB role.** Every `config/env.*.yaml` DSN points to a SELECT-only-granted role. Documented in `env.example.yaml` comments; deployment concern, not code-enforced.

**Layer 2 — wrapper class.** `shared/db/readonly_client.py` is the only sanctioned DB access path for test/assertion code:

```python
_STATEMENT_VERBS = {"select", "with", "explain", "show", "describe", "table", "pragma"}
_WRITE_TOKENS = ("insert", "update", "delete", "merge", "copy")   # WITH can wrap DML CTEs

class ReadOnlyDBClient:
    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        head = sql.lstrip("( \n\t").split(None, 1)[0].lower().rstrip(";")
        if head not in _STATEMENT_VERBS:            # leading-keyword allow-list,
            raise PermissionError(f"Blocked by ReadOnlyDBClient: {sql[:80]!r}")
        lowered = sql.lower()                        # `with`/`explain` get a second look:
        if any(t in lowered for t in _WRITE_TOKENS) or "analyze" in lowered:
            raise PermissionError(...)               # fail closed; EXPLAIN ANALYZE executes
        return self._conn.execute(sql, params).fetchall()
```

Design change vs v1.0: the denylist regex scanned the whole statement and false-blocked legitimate reads containing words like `'INSERT'` inside string literals; an allow-list on the statement's leading keyword fixes the common false positive without a SQL-parser dependency. Multi-statement strings (e.g. `"SELECT 1; DROP TABLE x"`) are rejected outright by refusing any `;` followed by non-whitespace. Known sharp edge (kept deliberately): the token scan over `WITH`/`EXPLAIN` statements is substring-based and therefore *over*-blocks reads whose literals merely mention write words — acceptable because the DB role is authoritative anyway, failing closed beats parsing SQL, and an implementation may refine it with a real tokenizer as long as every data-modifying-CTE fixture still fails (Roadmap 5.2). The connection object comes from a driver chosen per target app (Medusa ⇒ PostgreSQL, e.g. psycopg) — v1.0's `import httpx` comment was a placeholder error.

**Layer 3 — static scans.**
- Pre-commit: `check_db_readonly.py` scans `shared/db/**` for write verbs appearing as executable code identifiers; uses the unified denylist (`INSERT UPDATE DELETE MERGE REPLACE UPSERT CALL EXEC COPY GRANT ALTER DROP TRUNCATE CREATE`), implemented over AST tokens so string/comment literals don't trip it; explicit escape hatch only via reviewed `# db-write-ok: <reason>` (used solely by the checker's own unit tests).
- CI additionally scans `automation/` + `shared/assertions/`: **any direct import of DB drivers** (`psycopg`, `pymysql`, `sqlite3`, …) fails, ensuring every query flows through the wrapper. Scope now matches everywhere (v1.0 said `shared/db/` in one place and whole-tree elsewhere).

---

## 7. Configuration & Notification

### 7.1 Config loading (`shared/config/settings.py`)

```python
class AuthConfig(BaseModel):
    username: str
    password: str

class DBConfig(BaseModel):
    dsn: str

class EnvConfig(BaseModel):
    base_url: str
    api_base_url: str | None = None     # 可选：UI/API 组合执行时使用独立 API 地址
    auth: AuthConfig | None = None      # optional: guest flows need neither auth nor db
    db: DBConfig | None = None
    cookies: dict[str, str] = {}

def load_env(env_name: str | None = None, cli_flag: str | None = None) -> EnvConfig:
    # precedence: CLI --env > TEST_ENV env var > "local"
    env_name = cli_flag or os.environ.get("TEST_ENV") or "local"
    path = Path(f"config/env.{env_name}.yaml")
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — copy config/env.example.yaml")
    data = yaml.safe_load(path.read_text()) or {}   # empty-file guard (safe_load returns None)
    return EnvConfig(**data)
```

Fixes vs v1.0 snippets: `--env` precedence actually implemented (was prose-only); empty YAML no longer crashes; `auth`/`db` optional to support guest-checkout flows。可选的 `api_base_url`/`ARGUS_API_BASE_URL` 在站点和后端使用不同地址时保持生成 API 夹具与环境解耦。

**prod protection is layered** (`check_prod_scope.py` + conftest + DB role): when `TEST_ENV=prod`, root `automation/conftest.py` implements `pytest_collection_modifyitems` to deselect every item lacking `@pytest.mark.read_only`; on top of collection gating, `scripts/check_prod_scope.py` statically audits read-only-marked tests for write-shaped client/page calls (configurable method denylist) before a prod run is assembled. Honest scoping: the marker is classification metadata that generation self-reports, so these code layers are defense-in-depth *around* the real boundaries — the SELECT-only DB role and host-side network/tenant controls. Combined they catch misconfiguration; no single layer is trusted alone.

### 7.2 Notification

Unchanged strategy pattern: `Notifier` ABC; channel implementations DingTalk/Feishu/WeCom/Email; dispatcher fans one run result to all configured channels; per-channel retry with exponential backoff (1s/2s/4s); a failing channel is logged and never blocks others nor the run. Entrypoints are unified (v1.0 had two competing ones): `shared/notify/dispatcher.py` holds the logic, `scripts/notify.py` is the CLI wrapper consuming a run's `run-summary.yaml` (explicit path, or `auto` = the newest `iterations/<id>/runs/<run-id>/run-summary.yaml`) or a CI job status. CI invokes it under `if: ${{ always() }}` so failures notify too (a plain step after a failed step would be skipped), and notification steps themselves carry `continue-on-error: true` per best-effort policy。只有当前任务已产出 JUnit 时才允许选择 `auto` 摘要；环境启动等前置失败没有 JUnit 时，必须直接发送当前 `e2e` job 状态，禁止误用历史 iteration 摘要。

### 7.3 Extending environments/channels

- New environment: add gitignored `config/env.<name>.yaml` matching `EnvConfig`; zero code change.
- New channel: implement `Notifier`, register in `dispatcher.py`'s channel map, extend `config/notify.example.yaml`. One intentional code-touch point keeps the fan-out explicit.

---

## 8. CI Shape (summary; task details in Roadmap Phase 7)

Two jobs, deliberately split because their prerequisites differ:

- **static-checks**: schema validation (including the exact `00-raw/source-payload.yaml` path), state/staleness validation, `--tier from-iteration` coverage, orphan-test closure, export semantics, layering/POM/API-model/markers checks, DB-readonly scan, secret scan, patch-scope fixtures, ruff/pyright. Needs no target app and runs on every PR.
- **e2e**: boots the pinned target-app harness (compose + seed + healthcheck), injects secrets to generate `config/env.ci.yaml`, executes the suite, records the CI run summary via `self_debug_helper.py record-ci-auto` (sole summary writer on CI — scans eligible iterations, reads JUnit, writes `scope: full` with one attempt), uploads `reports/` 与各 iteration 的 run 证据（重型日志/trace 仅作为 artifact，规则见 ADR-012），and notifies under `always()`. It is required for every PR targeting `release`; for other PRs it runs when `automation/**` or `iterations/**` changes; unrelated PRs run static checks only. A **weekly scheduled run** executes the full suite against `release` HEAD, catching non-PR drift (upstream image digests, runner/Chromium upgrades, lockfile drift); this doubles as the cost-containment option if PR-level e2e proves too expensive (see Open Questions). A non-flaky weekly failure notifies the designated channel; **two consecutive** failures open a tracking issue (when token permissions allow); merge protection stays PR-scoped and is never keyed to scheduled runs.
- **Flake policy (CI-side, distinct from the in-test retry ban)**: a failed e2e job is re-run once automatically; a retry-pass marks the notification as `flaky-suspect` (single category, never counted green, never blocks merge on its own); the same nodeid appearing flaky-suspect repeatedly is recorded to `knowledge/patterns.md` via the M12 channel and triggers a repair-or-escalate decision. Full quarantine workflows stay post-v1 (Deferred).

Workflow-hardening contract (GitHub's own guidance): third-party actions are pinned to **full commit SHAs** (`<sha> # vX.Y` comments; Dependabot keeps them current), top-level `permissions` default to none with per-job opt-in, every job sets `timeout-minutes`, and PR workflows share a concurrency group that cancels superseded runs.

CI trigger and notification contract:

| PR context | static-checks | e2e | notification |
| --- | --- | --- | --- |
| Any PR | required | — | static-checks result under `always()` |
| PR targeting `release` | required | required | static-checks and e2e under `always()` |
| Other PR changing `automation/**` or `iterations/**` | required | required | static-checks and e2e under `always()` |
| Other PR with no automation/iteration change | required | not run | static-checks under `always()` |

---

## 9. Key Structural Decisions (ADR index)

| Decision | ADR |
| --- | --- |
| Single long-lived `release` branch; PR-only merges from `test/<iteration-id>` | [ADR-001](./adr/adr-001-single-release-branch.md) |
| Medusa pinned as first target app | [ADR-002](./adr/adr-002-medusa-first-target-app.md) |
| Skills vendored in-repo for v1 | [ADR-003](./adr/adr-003-vendored-skills-deferred-to-post-v1.md) |
| Self-debug session-side only; CI never patches tests | [ADR-004](./adr/adr-004-self-debug-is-session-side-only.md) |
| Sparse traceability rows, derived coverage | [ADR-005](./adr/adr-005-derived-coverage-sparse-traceability.md) |
| Source-payload plugin envelopes on a disk-first boundary | [ADR-006](./adr/adr-006-source-payload-boundary.md) |
| Consolidated repo layout: 6 skills, plugins layer, iterations↔module split, YAML sources + derived views | [ADR-007](./adr/adr-007-repo-layout-redesign.md) |
| Namespaced test data and worker-isolated fixtures for parallel execution | [ADR-008](./adr/adr-008-parallel-test-isolation.md) |
| Accepted artifacts are immutable; exemptions and explicit reopen are separate contracts | [ADR-009](./adr/adr-009-exemptions-and-accepted-artifact-reopen.md) |
| Per-run evidence directories under `iterations/<id>/runs/<run_id>/` | [ADR-010](./adr/adr-010-per-run-evidence-directories.md) |
| `accepted` closes the PR; `merged` is finalized post-merge by script | [ADR-011](./adr/adr-011-post-merge-finalization.md) |
| Tiered evidence storage: summaries/patches in git, heavy evidence as artifacts | [ADR-012](./adr/adr-012-evidence-storage-policy.md) |

CI skeletons referenced by §8's jobs (merged from the former Implementation Guide §5 on 2026-08-27):

```yaml
# .github/workflows/ci.yml — static checks, every PR, no target app needed
# (regression.yml additionally carries `on: schedule:` — weekly full run against release HEAD)
permissions: {}                        # minimal by default; jobs opt in explicitly
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  static-checks:
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@<full-sha>        # v4 — pin exact SHA; Dependabot updates
      - uses: astral-sh/setup-uv@<full-sha>      # v5
      - run: uv sync --group dev
      - run: uv run pre-commit run --all-files   # schemas/state/staleness/POM/
                                                  # models/markers/db/secrets/lint
      - run: uv run pytest scripts/tests          # framework's own suites
                                                  # includes schema-block and patch-scope fixtures
      - run: uv run python scripts/check_coverage.py --tier from-iteration
      - if: always()
        continue-on-error: true
        run: uv run python scripts/notify.py --job static-checks

# .github/workflows/regression.yml — e2e for release PRs or automation/iteration changes
# Target-app provisioning is compose-only; target_app_up.py owns the full stack.
permissions:
  contents: read
concurrency:
  group: e2e-${{ github.ref }}
  cancel-in-progress: true
jobs:
  e2e:
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@<full-sha>
      - uses: astral-sh/setup-uv@<full-sha>
      - run: uv sync --group dev
      - run: uv run playwright install --with-deps chromium
      - run: uv run python scripts/target_app_up.py
      - run: uv run python scripts/target_app_healthcheck.py
      # secrets reach the assembly step via the workflow `env:` block mapped from ${{ secrets.* }} —
      # never as shell arguments, never via inline echo (log-tracing would leak them);
      # settings.py reads env-var overrides first, so most jobs never need the YAML at all
      - run: uv run python -m shared.config.settings assemble --env ci   # writes gitignored config/env.ci.yaml
      - run: TEST_ENV=ci uv run pytest automation/web automation/api --junitxml=reports/junit.xml
      - run: uv run python scripts/self_debug_helper.py record-ci-auto --junit reports/junit.xml --env ci
      # 首次失败只复跑一次；复跑转绿时 job 依据复跑结果放行，但通知分类保持 flaky-suspect
      - if: always()
        uses: actions/upload-artifact@<full-sha>   # v7（Node 24）
        with:
          name: run-evidence-${{ github.run_id }}
          path: |
            reports/
            iterations/*/runs/
      - if: always()
        continue-on-error: true
        run: uv run python scripts/notify.py --summary auto   # resolves newest iterations/<id>/runs/<run-id>/run-summary.yaml
      - if: always()
        run: uv run python scripts/target_app_down.py
```
