# Product Requirement Document (PRD)

## AI-Driven Automation & Performance Testing Framework

Version: 1.1 · Status: Revised baseline (v1.0 + review adoptions) · Companion docs: ARCHITECTURE.md, DATA_MODEL.md, GLOSSARY.md, ROADMAP.md

> **Reading rule**: machine contracts (JSON Schemas, field dictionaries) are defined authoritatively in [DATA_MODEL](../architecture/DATA_MODEL.md); IDs and naming formats in [GLOSSARY.md](./GLOSSARY.md). This PRD defines *what* and *in which state*; it does not restate schema fields.

---

## 1. Purpose & Scope

Define **what** the system must do and **in what order/state**, independent of implementation. This PRD is the contract the Skills, scripts, and CI gates must all satisfy. Scope is v1: requirement clarification through Web + API automation generation and self-debug execution for a single target application, single repo. Mobile, mini-program, performance testing, and real plugin integrations are designed-for but not required to ship in v1 (see §8).

**Roles** (minimum viable): the **user** is the only actor who can accept requirements/test points, provide environment secrets, approve skill edits, merge to `release`, and review self-debug diffs at acceptance. The **agent** drives generation, validation, and the self-debug loop, but never performs an acceptance action without a persisted user-confirmation record (see §6 Auditability). A CI job is a checker only — it can fail builds, never accept or merge.

---

## 2. System Overview & Core Data Flow

### 2.1 Core entities

|Entity|Identity|Lives in|Produced by|
|---|---|---|---|
|IterationState|`iteration_id`|`iterations/<id>/iteration.yaml`|`scripts/new_iteration.py`; updated by skills/scripts at each phase transition|
|Requirement|`requirement_id` (R####)|`requirements.yaml`|test-design skill, stage 1|
|TestPoint|`test_point_id` (T####)|`test_points.yaml`|test-design skill, stage 2|
|FunctionalCase|`case_id` (C####)|`functional-cases.yaml`|test-design skill, stage 3|
|NormalizedSpec|— (endpoint list under `endpoints[]`)|`api/spec.normalized.yaml`|api-test-design skill / plugin conversion (M4)|
|APICase|`api_case_id` (A####)|`api/cases.yaml`|api-test-design skill|
|AutomationTest|`automation_test_id` (pytest nodeid)|`automation/**/tests/<module>/`|web/api-automation-generation skills|
|TraceabilityRecord|link row (`requirement_id` → `test_point_id` → `functional_case_id` xor `api_case_id` → `automation_test_ids[]`)|`traceability.yaml`|all generation skills, incrementally (idempotent upsert keyed on `iteration_id`+ids)|
|RunResult|`run_id`|`run-summary.yaml` + `reports/allure-results/`|self-debug-runner|

Full field dictionaries: DATA_MODEL §2–§10.

### 2.2 End-to-end data flow

```
[raw input]                 [plugin payload]  ── persists ──▶ 00-raw/source-payload.yaml
        │                          │                        (validated against source-payload schema)
        ▼                          ▼
 ┌─────────────────────────────────────────┐   requirements.yaml   ┌──────────────┐
 │ test-design (stage 1 = M1)              │──────────────────────▶│ requirement.md│ (rendered)
 └─────────────────────────────────────────┘                        └──────────────┘
        │ (user accepts — recorded in iteration.yaml approvals[])
        ▼
      M2: test_points.yaml ──▶ test_points.md            (user accepts)
        ▼
 ┌───────────────────────────┐        ┌────────────────────────────────────┐
 │ M3: functional-cases.yaml │  OR/AND│ M4: source/HAR/plugin payload       │
 │     exports/*.xmind       │        │     → api/spec.normalized.yaml      │
 └───────────────────────────┘        │ M5: api/cases.yaml → *.xlsx         │
        │                             └────────────────────────────────────┘
        ▼                                        │
      M6: web POM + tests                        ▼
                                       M7: api clients/models/tests
        └───────────────┬──────────────────────┘
                        ▼
             M9: self-debug-runner
                        ▼
   run-summary.yaml + reports/allure-results/
                        ▼
     user acceptance (diffs reviewed) ──▶ merge test/<iteration_id> -> release
```

Every arrow that crosses a skill boundary is a **YAML file validated against a schema** — never free text and never an in-memory handoff. Plugin payloads are no exception: `run_plugin.py` writes the normalized payload to disk first, validates it against the *source-payload* schema, and only then hands the path to a skill (see M14). This is what lets any step be re-run, audited, or taken over by a human without losing state.

---

## 3. Functional Module Breakdown

|#|Module|Purpose|Trigger|Primary Input|Primary Output|Confirmation point|
|---|---|---|---|---|---|---|
|M1|Requirement Ingestion & Clarification|Turn raw/messy input into an unambiguous requirement|New iteration created|`00-raw/*` or plugin source payload|`requirements.yaml` + rendered `requirement.md`|⏸ Yes (clarify, then accept)|
|M2|Test Point Extraction|Enumerate testable points from accepted requirement|M1 accepted|`requirements.yaml` (status `accepted`)|`test_points.yaml` (+ rendered `.md`)|⏸ Yes|
|M3|Functional Test Case Generation|Turn test points into structured, exportable cases|M2 accepted|`test_points.yaml` (status `accepted`)|`functional-cases.yaml` + `.xmind`|No (schema-gated; see §4.3 note on implicit review opportunity)|
|M4|API Spec Normalization|Turn source code / docs / HAR / plugin payload into a normalized spec|Iteration needs API cases|source, docs, `.har`, or API source payload|`api/spec.normalized.yaml`|No|
|M5|API Test Case Generation|Turn normalized spec into structured API cases|M4 output present|`api/spec.normalized.yaml` (valid)|`api/cases.yaml` + `.xlsx`|No (schema-gated only)|
|M6|Web Automation Generation|Turn functional cases into POM-based UI automation|M3 output present|`functional-cases.yaml` (status `exported`)|page/component objects + tests under `automation/web/{pages,components,tests}/<module>/`|No|
|M7|API Automation Generation|Turn API cases or HAR into httpx+pydantic automation|M5 output present, **or** a HAR (which is routed through M4's normalization to produce schema-valid `api/cases.yaml` before any code is written)|`api/cases.yaml` (valid)|clients + models + tests under `automation/api/`|No|
|M8|Environment Setup|Persist real env parameters for execution|Before first run|user-provided values|`config/env.<name>.yaml`|⏸ Yes|
|M9|Execution & Self-Debug|Run generated suite, autonomously fix whitelisted failure classes, stop at green/budget/escalation|M6 and/or M7 output present + M8 complete|test files + env config|`run-summary.yaml`, allure results|No mid-loop; final summary + full diff history handed over|
|M10|Traceability & Coverage|Guarantee every non-exempt requirement reaches the tier its iteration stage demands|Continuous; staged gate in CI|all of the above|`traceability.yaml`, coverage verdict per §5.1|No (automated gate)|
|M11|Notification|Report run outcomes to IM channels|End of M9, or CI completion (always, incl. failures)|`run-summary.yaml` or job result|DingTalk/Feishu/WeCom/Email message via `shared/notify/dispatcher.py` (CLI wrapper `scripts/notify.py`)|No|
|M12|Knowledge Accumulation|Record reusable facts/lessons|**Concrete trigger**: within 24h of each terminal state of M9 and after every applied skill optimization|agent observations|append-only entries in `knowledge/*.md` with frontmatter (`tags/date/source`)|No|
|M13|Skill Self-Optimization|Improve a Skill's own instructions|Same failure class recurs in ≥2 distinct iterations (quantified threshold), or ≥3 occurrences anywhere|proposed SKILL.md diff|versioned, committed skill change (old copy kept under `versions/`)|⏸ Yes|
|M14|Plugin Ingestion|Fetch + normalize external sources|Skill needs external data|source ref (URL/ID/path)|normalized payload written to disk matching `*_source_payload.schema.json`; downstream M1/M4 converts it into internal artifacts|No (plugin has no confirmation point; downstream M1/M4 still gate)|

---

## 4. Phase-by-Phase I/O Standards & State Machines

Each phase defines: **Entry precondition**, **Input**, **Output**, **State diagram**, **Validation rules**, **Failure handling**. Status values below are serialized lowercase snake_case (GLOSSARY "ID & Naming Formats"); prose capitalization is presentational only.

### 4.1 Requirement Clarification (M1)

- **Entry precondition**: iteration directory exists (`scripts/new_iteration.py` has run, creating `iteration.yaml` with status `created`); `00-raw/` is non-empty OR a source payload was written by `run_plugin.py`.
- **Input**: unstructured text/files, or a plugin payload already matching `requirement_source_payload.schema.json` (ambiguities allowed).
- **Output**: `requirements.yaml` (status progressing `draft` → `clarifying` → `clarified` → `accepted`), rendered to `requirement.md`.

**Clarification interaction protocol** (binding for the agent):

1. Ask at most **3 highest-priority questions per round**; defer lower-priority ambiguities to later rounds.
2. Wherever possible offer options A/B (**never a mixed recommendation**) and explicitly recommend one.
3. An ambiguity may be marked resolved only from a user answer or explicit user statement — never from an invented assumption.

**State diagram**

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`draft`|raw input present, no extraction yet|first extraction pass complete → `clarifying`|Agent|
|`clarifying`|≥1 unresolved ambiguity|user resolves all listed ambiguities → `clarified`|Agent asks, User answers|
|`clarifying` (fast path)|first pass finds zero ambiguities|→ `clarified` directly (recorded as an event)|Agent|
|`clarified`|no unresolved ambiguity remains, schema valid|user explicitly accepts → `accepted` (approval event appended)|User|
|`accepted`|user confirmation recorded|unlocks M2. User-requested change later → back to `clarifying` (re-open); staleness propagation applies (§6)|User|

- **Validation rules**: schema-valid; every requirement has `requirement_id`; when status ∈ {`clarified`,`accepted`} no entry may have `resolved: false`, and every resolved entry carries a non-empty `resolution`. Already-resolved entries are **kept** (they are audit evidence), not deleted.
- **Failure handling**: if the agent cannot resolve an ambiguity without a guess, it stays in `clarifying` and asks — never auto-advances.

### 4.2 Test Point Generation (M2)

- **Entry precondition**: `requirements.yaml` status = `accepted`.
- **Input**: `requirements.yaml`.
- **Output**: `test_points.yaml` (statuses `draft` → `review` → `accepted`), rendered to `test_points.md`.

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`draft`|requirement accepted|extraction complete → `review`|Agent|
|`review`|schema valid|user reviews → `accepted`, or → `draft` (revise)|User|
|`accepted`|user confirms|unlocks M3; also unlocks the R→T coverage tier check (§5.1)|—|

- **Validation rules**: every requirement with default flags (i.e., not manually exempted) is referenced by ≥1 test point **at this stage** — gaps are caught here, not deferred to final CI. A requirement judged un-testable gets `testable: false` + reason; one that will never be automated gets `automation_required: false` + `manual_reason` — both remain visible to reviewers.
- **Failure handling**: unmappable requirements are flagged in the review output, never silently omitted.

### 4.3 Functional Test Case Generation (M3)

- **Entry precondition**: `test_points.yaml` status = `accepted`.
- **Input**: `test_points.yaml`.
- **Output**: `functional-cases.yaml` (statuses `draft` → `validating` → `valid` → `exported`) + `exports/<Project>_v<N>_Cases.xmind`.

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`draft`|test points accepted|cases written → `validating`|Agent|
|`validating`|draft complete|schema+semantic check → `valid`, else → `draft` (fix loop, budget 3 then surface)|Agent (automatic)|
|`valid`|schema passes|export script runs → `exported`|Agent (automatic)|
|`exported`|`.xmind` written and structurally verified|unlocks M6|—|

- **Validation rules**: schema valid; every case's tags include exactly one `module:<name>` tag matching GLOSSARY module format; every case links its source test points (`test_point_ids[]`). Exporters must be byte-reproducible (fixed ZIP timestamps — Architecture §7).
- **Implicit review opportunity**: M3 itself is not a confirmation gate by design; because M6 is a separately invoked skill, the exported `.xmind` naturally serves as a human-readable checkpoint the user may reject before invoking generation. The agent should surface the export path at handoff instead of immediately proceeding.

### 4.4 API Spec Normalization & API Test Case Generation (M4 + M5)

- **Entry precondition**: iteration needs API coverage; a source exists (code, dev docs, HAR, or an `api_source_payload` written by `run_plugin.py`).
- **Output**: `api/spec.normalized.yaml` → `api/cases.yaml` (statuses per artifact) + `exports/<Project>_v<N>_API_Cases.xlsx`.

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`spec_draft`|source available|normalization complete → `spec_valid`, else retry (budget 3, then surface)|Agent|
|`spec_valid`|matches `api_spec.schema.json`|case generation runs → `cases_draft`|Agent|
|`cases_draft`|cases written|schema check → `cases_valid`, else fix loop|Agent|
|`cases_valid`|schema + semantic checks pass|export runs → `exported`|Agent|
|`exported`|`.xlsx` written|unlocks M7|—|

- **Validation rules**: every endpoint not marked `out_of_scope: true` (with a reason) has ≥1 happy-path case **and** ≥1 negative/edge case, checked by `scripts/check_api_coverage.py`; every case carries a required `module` (drives `automation/api/tests/<module>/` placement).
- **Failure handling**: unparseable source stops at `spec_draft` and surfaces to the user — hard failures are not silent even though this phase has no confirmation point.

### 4.5 Web UI Automation Generation (M6)

- **Entry precondition**: `functional-cases.yaml` status = `exported`.
- **Output**: page/screen objects + tests under `automation/web/{pages,components,fixtures,tests}/<module>/`, plus incremental idempotent-upsert updates to `traceability.yaml`.

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`generating`|cases exported|POM code + tests written → `linting`|Agent|
|`linting`|generation complete|`check_pom_boundary.py` + `check_test_markers.py` + ruff + pyright pass → `generated`, else fix loop|Agent (automatic)|
|`generated`|lint clean|unlocks M9 for this module|—|

- **Validation rules**: no selector literal in a `tests/` file; no assertion inside `pages/`–`components/` code; every test tagged with `module`/`case_id`/`iteration` markers (markers are metadata — run selection is by module **directory**); `traceability.yaml` gains an `automation_test_ids` entry for every covered `case_id`.
- **Failure handling**: a case with no sensible UI mapping is flagged back to the user rather than producing a vacuous test.

### 4.6 API Automation Generation (M7)

Same shape as 4.5; input `api/cases.yaml` (or a HAR pre-normalized through M4/M5). Output adds `automation/api/{clients,models}/<module>/`. Additional enforcement: every generated client method references pydantic request/response models — no raw `dict` payloads (statically checked by `check_api_models.py`).

### 4.7 Execution & Self-Debug (M9)

- **Entry precondition**: automation for the target modules is `generated`; required `config/env.*.yaml` values present (M8 complete).
- **Scope**: one invocation targets one **module set** within the iteration (default: all modules touched by this iteration). Re-runs execute the failing subset plus its intra-module dependencies, never gratuitous full-suite reruns.
- **Output**: `run-summary.yaml` (with `run_id`), `reports/allure-results/`.
- **Runtime rule**: the self-debug loop is **session-side only** (agent-driven skill). CI never runs self-debug — CI executes committed tests read-only.

|State|Entry condition|Exit condition → Next state|Actor|
|---|---|---|---|
|`running`|tests + env ready|suite executes → `passed` or `failed`|Automatic|
|`failed`, fixable class, budget remaining|attempt classified auto-fixable|patch applied → verification battery → `running`|Agent (automatic, no user contact)|
|`failed`, escalation class, or two consecutive attempts with near-identical diffs|see taxonomy below|→ `escalated` (stop regardless of remaining budget)|Agent (automatic)|
|`passed`|0 failures|→ hand back to user for acceptance **with full attempt diff history**|Agent|
|`budget_exceeded`|budget exhausted without escalation trigger|→ hand back with diagnosis|Agent|
|`escalated`|disallowed patch class detected, or environment/product-mismatch class observed|→ stop, report classified diagnosis; user decides|Agent|

**Patch scope (hard rule):**

- May modify: `automation/web/{pages,components,fixtures}/**`, `automation/api/{clients,models}/**`, generated test implementation internals (waits, selectors inside page objects, import paths), shared utilities it owns.
- Must never modify: assertions' expected values or assertion semantics, expected results sourced from `cases.yaml`, markers/tags, pytest collection config, `iterations/**`, `config/**`, `.agents/skills/**` (incl. schemas), `AGENTS.md`.
- Banned patterns: `pytest.skip`/`pytest.xfail`/`@pytest.mark.skip|xfail`, `assert True`, bare `try/except Exception: pass`, deleting or loosening existing assertions, moving tests out of collection.

**Failure-class taxonomy:**

| Class | Auto-fix? | Typical repair |
| --- | --- | --- |
| `locator_drift`, `timing`, `fixture_error`, `serialization_error`, `import_type_error` | ✅ yes | update selectors/waits/fixtures/serialization/types |
| `data_issue` (test data missing/consumed) | ⚠️ only via seeding hooks (`shared/testdata/`); never by weakening expectations | re-seed namespace, unique-suffix data |
| `environment_unavailable`, `auth_failure`, `backend_5xx`, `product_behavior_mismatch`, `requirement_conflict` | ❌ escalate immediately | diagnose and hand over |

**Post-patch verification battery** (every cycle, before re-run): ruff + pyright + `check_pom_boundary.py` + `check_test_markers.py` + affected-module regression. A patch failing static gates counts against budget and is reverted if not clean.

- **Validation rules**: `retry_budget` default 5 debug cycles per invocation; every appends `{attempt_number, result, failure_class, summary, diff_ref}` to `run-summary.yaml.attempts[]`.
- **Failure handling**: the user is contacted only at terminal states (`passed`/`budget_exceeded`/`escalated`) — never mid-loop. At acceptance the user reviews the accumulated diffs; the acceptance criterion is that no diff touches forbidden scope.

---

## 5. Global Iteration State Machine

The global state is **persisted in `iterations/<id>/iteration.yaml`** (single field `state`, plus `blocked_reason`, per-artifact `artifacts{}` map, append-only `approvals[]` and `events[]`; full shape in DATA_MODEL §3). It aggregates phase states for dashboards/CI. Routes are branch-aware:

```
UI-led route:
CREATED → requirements_clarifying → requirements_accepted → test_points_review
  → test_points_accepted → functional_cases_generating → functional_cases_exported
  → web_automation_generating → web_automation_generated
  → env_pending → env_configured → executing → execution_passed | execution_budget_exceeded | escalated
  → acceptance_pending → accepted → merged

API-led route (skips M2/M3 entirely):
CREATED → requirements_clarifying → requirements_accepted → spec_normalizing → spec_valid
  → api_cases_generating → api_cases_exported
  → api_automation_generating → api_automation_generated
  → env_pending → env_configured → executing → …(same tail)

Hybrid: both case branches proceed in parallel; `executing` requires all intended branches
to have reached *_automation_generated. Which branches are intended is declared once in
iteration.yaml.branches at creation time.
```

Any state may move to `blocked` with a `blocked_reason` on a hard failure (spec parse failure, escalated self-debug, etc.). Leaving `blocked` always requires user action. Transition legality is enforced against this section's routes by scripts and referenced from AGENTS.md; illegal transitions are a validation error.

### 5.1 Staged coverage gates (resolves the strictness contradiction)

Coverage demands scale with the iteration's own progress; CI evaluates **per-iteration**, and the full `automated` tier is only demanded where it is meaningful:

| Iteration condition | Enforced minimum (via `check_coverage.py --tier <t>`) |
| --- | --- |
| test_points accepted | Tier R→T: every requirement (except `testable: false`) cited by ≥1 test point |
| functional and/or api cases exported | Tier T→C: every test point cited by ≥1 case |
| automation generated | Tier C→automation: every case whose requirement chain has `automation_required: true` maps to ≥1 nodeid |
| merged to release | All three tiers hold for the merged iteration |

Referential integrity (every referenced ID exists; IDs unique per scope; no orphan rows) is enforced at **every** tier. Requirements marked `automation_required: false` need `manual_reason` and exit the automated-tier demand.

---

## 6. Non-Functional Requirements

- **Determinism of derived views**: `.xmind`/`.xlsx`/`.md` renders must be byte-reproducible from their source YAML — exporters pin ZIP entry timestamps and document properties so two runs produce identical bytes (DoD: SHA-256 equal across runs). Determinism is promised **only** for these script-rendered outputs.
- **Regeneration discipline (skills)**: exact idempotency is not assumed from an LLM. Instead: each generated artifact records `generated_from: {artifact, sha256}`; when invoked on unchanged input (hash match) a generation skill defaults to a **no-op** unless explicitly forced; stable ordering and preserved ID allocation prevent gratuitous churn; outputs are formatted uniformly.
- **Auditability**: every confirmation-gated transition is reconstructable from `iterations/<id>/` alone: `approvals[]` records `{stage, action, actor=user, timestamp, artifact_sha256, note}`, and `events[]` records transitions. Raw text inputs under `00-raw/` are committed (subject to a pre-commit secret-pattern scan); binaries/large files are gitignored but must appear in `iteration.yaml.source_manifest[]` with `{path, sha256, captured_at}` so provenance survives redaction.
- **Staleness propagation**: when an upstream artifact changes (hash mismatch vs downstream's `generated_from.sha256`), downstream becomes stale: validators mark it, CI refuses stale assets, old exports must not ship, and affected automation must be regenerated or explicitly re-confirmed.
- **Security posture**: lightweight by explicit decision — secrets live in gitignored YAML (accepted v1 debt; migration path noted in RISKS_AND_KNOWN_ISSUES). Secrets/redaction rules: Authorization/Cookie/token-style headers and credential-shaped fields are redacted at ingestion boundaries (HAR normalization, case import, log/Allure attachment). DB access is read-only-only, with the read-only DB role as the authoritative control and code checks as defense-in-depth. `TEST_ENV=prod` mechanically restricts collection to tests marked `@pytest.mark.read_only` (enforced in conftest collection hook), not merely by prose.
- **Extensibility**: M14 plugins and mobile/mini-program/perf additions must not require modifying M1–M9's schemas or state machines. Vision-driven/UI-TARS style locator engines and global RTM aggregation are reserved extensions (out of scope, §8).
- **Browser matrix**: v1 validates Chromium only, locally and in CI (single-browser parity beats divergent installs).

## 7. v1 Acceptance Criteria

Aligned with Roadmap Phase 9; a release can claim v1 when all hold:

1. Two independent iterations have gone end-to-end from raw requirement to merged, passing, traceable automation — one UI-led, one API-led — with **no hand-written test code** (only requirement text and configuration).
2. Every confirmation-gated transition in those iterations is reconstructable from their `iterations/<id>/` directories alone (approvals + events + manifests present).
3. `check_coverage.py` proves all four tiers for both merged iterations; `must-automate` exemptions carry reasons.
4. Self-debug transcripts show zero mid-loop user contact and zero patches touching forbidden scope (audit rule §4.7 verified by diff review of `attempts[].diff_ref`).
5. CI green on GitHub Actions: static-checks job (schemas, layering, POM boundary, DB read-only, secret scan, coverage tiers) on every PR; e2e job executing the suite against the pinned local target-app harness.

---

## 8. Out of Scope for v1

- Real plugin implementations (Zentao/Jira/TAPD/Lanhu/Figma/Postman) — interface + source-payload schemas only.
- Mobile (Appium) and Mini-program (Minium) automation generation — directories and dependency groups reserved, generation skills not shipped.
- Performance/load test generation from functional cases (Locust scripts hand-authored in v1; locust itself lives in an optional dependency group).
- Web platform/dashboard UI — CLI + file-based state only.
- `knowledge/` categorization/scoring/expiry — flat files with frontmatter metadata only.
- Self-debug inside CI pipelines; automated container sandboxing/virus-scanning of generated code (execution happens in the developer's project environment; bandit-style scans reserved as post-v1 hardening).
- Vision-model-driven element location (Midscene/UI-TARS style), cross-repo RTM aggregation services.
