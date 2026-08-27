# Task Implementation Roadmap

## AI-Driven Automation & Performance Testing Framework

Version 1.1 · Companion docs: PRD.md, ARCHITECTURE.md, DATA_MODEL.md

How to use this doc with a coding agent: work one task at a time, in order within a phase; paste the task line + its Definition of Done (DoD) as the instruction; don't start the next task until the current DoD is verifiably met. Phases are sequential; tasks inside "Parallelizable" groups can run concurrently. Verification commands reference [ENVIRONMENT_SETUP.md](../engineering/ENVIRONMENT_SETUP.md); test-layer semantics reference [TESTING_STRATEGY.md](../engineering/TESTING_STRATEGY.md). Tasks marked **[manual gate]** are human acceptance checkpoints executed in an agent session (they cannot be automated as plain script DoDs).

---

## Phase Overview & Dependencies

| Phase | Delivers | Depends on | Exit condition |
| --- | --- | --- | --- |
| 0 Infrastructure | toolchain, scaffolding, AGENTS.md | — | fresh clone → `make setup` → `make new-iteration ID=x` yields lint-clean skeleton, zero manual steps |
| 1 Contracts & Guardrails | schemas, registry, every checker proven by fixtures | 0 | all mechanical gates enforced & fixture-proven **before any AI generation touches the repo** |
| 2 Plugin Skeleton | envelope contracts + failing-safe runner | 1 | contract enforced by failure mode, zero real plugins |
| 3 Skill: test-design | requirement→points→cases→xmind | 1 | one requirement through all confirmation points, exported & valid |
| 4 Skill: api-test-design | spec→api cases→xlsx | 1 | same bar for API path |
| 5 Web Automation + Self-Debug (+ target-app harness) | harness first, then generated web suite closing the loop | 3 | one case: passing POM-compliant traceable web test, no hand-coding |
| 6 Skill: api-automation-generation | API codegen loop | 4,5 | same bar for API path |
| 7 CI Wiring | static job green always; e2e job executing against harness | 1,5,6 | merge to `release` gated full pipeline; notifications fire |
| 8 Knowledge + Self-Optimization | recorded lessons, guarded optimizer | 3–6 | optimizer fired end-to-end once with confirmation gate proven |
| 9 Real Iterations ×2 | UI-led + API-led merged | 0–8 | **v1 exit**: PRD §7 acceptance criteria all hold |

_Notes: v1.0 order defects fixed — target-app harness moved into Phase 5's opening (tests there previously demanded an app standing up only at Phase 9); `api_spec.schema.json`, state/staleness validator, marker/POM/model/secrets checkers added to Phase 1; phantom `-m agents.self_debug_runner` removed (self-debug is session-side, ADR-004)._

---

## Phase 0 — Infrastructure Setup

_Parallelizable: 0.1–0.6._

- [ ] **0.1** Init project with uv, Python pin 3.12 (uv writes `.python-version`; no second echo). **DoD**: clean checkout `uv sync` exits 0; `uv run python --version` = 3.12.x.
- [ ] **0.2** Write `pyproject.toml`: core deps pytest≥8.3, pytest-playwright≥0.5, pytest-xdist≥3.6, allure-pytest≥2.15, httpx≥0.27, pydantic≥2.9, rich≥13.9, pyyaml≥6.0, jsonschema≥4.23, openpyxl≥3.1; dev group ruff/pyright/pre-commit; optional groups mobile(appium)/perf(locust); pytest markers `module`,`case_id`,`iteration` registered with `--strict-markers`; ruff E,F,I,UP,B,SIM ll=100; pyright basic. **DoD**: `uv run ruff check . && uv run pyright` succeed on empty tree; `appium-python-client`/`locust` NOT installed by default (`uv sync` without groups).
- [ ] **0.3** Write `.pre-commit-config.yaml`: remote ruff hooks + local `validate-schema` (files `^iterations/.*\.yaml$` excluding `iterations/*/00-raw/**`), `validate-iteration-state`, `no-db-writes`, `check-secrets`. **DoD**: install + `run --all-files` passes on empty skeleton (nothing-to-check = exit 0).
- [ ] **0.4** Write `Makefile` per ENVIRONMENT_SETUP target table (`setup,new-iteration,validate-iteration,export,web-tests,api-tests,lint,target-app-*`). **DoD**: `make setup` completes (deps, chromium only, hooks). No `debug` target exists; `web-tests` selects by directory path.
- [ ] **0.5** Write `.gitignore`: env/notify secrets; `reports/**` + keeper re-include; `automation/api/har/**` + keeper; `config/env.ci.yaml`. **DoD**: dummy secrets file invisible to `git status`; `git add reports/` still stages `.gitkeep`.
- [ ] **0.6** Write full `AGENTS.md` (pipeline w/ confirmation points, hard rules incl. staleness re-open consequences, branching, clarification protocol ≤3 questions w/ recommendation, prod=read_only-marked-only) + one-line `CLAUDE.md` (`@AGENTS.md`). **DoD**: human sign-off; committed.
- [ ] **0.7** `scripts/new_iteration.py`: scaffold entire `iterations/<id>/` incl. `iteration.yaml` (`state: created`, declared branches) and template YAMLs w/ statuses; same-ID rerun errors clearly unless `--force` (force requires explicit re-typed confirmation); registers against `scripts/schema_registry.yaml`. **DoD**: produced tree diffs clean vs checked-in expected-tree fixture; duplicate call fails loudly; schema-bound fields present.
- [ ] **0.8** Directory skeleton w/ `.gitkeep`s exactly matching Architecture §2 (incl. `shared/config,testdata`, `plugins/_interface/schemas`, `scripts/schemas,tests`, `skills/*/versions`). **DoD**: structural diff vs doc tree clean.
- [ ] **0.9** Configure branch protection on `release` (PR-only, required status checks placeholder) per ADR-001. **DoD**: direct push attempt rejected (documented screenshot/log; settings-as-code where host supports).

## Phase 1 — Contracts, Registry & Guardrail Scripts

_Parallelizable: 1.1–1.14 all depend only on Phase 0; 1.15 last._

- [ ] **1.1** Author all schemas per DATA_MODEL §§2–10: requirements, test_points, functional_cases, api_spec, api_cases, traceability, run_summary, iteration, two source payloads. Placement: producing-skill `schemas/` / `scripts/schemas/` / `plugins/_interface/schemas/`. **DoD**: each validates a hand-written valid fixture and rejects an invalid one (missing required, bad enum/pattern, failed conditional like unresolved ambiguity at `accepted`) — pytest pairs in `scripts/tests/test_schemas.py`.
- [ ] **1.2** `scripts/schema_registry.yaml` + `validate_schema.py` using it exclusively. **DoD**: registered fixture tree exits 0; unregistered-yaml and wrong-schema cases exit non-zero naming exact JSON path; registry binding matches DATA_MODEL placement.
- [ ] **1.3** `scripts/validate_iteration.py`: transition legality vs PRD §5 routes + `blocked_reason` handling + staleness verdicts from `generated_from.sha256` chain + approval/event completeness. **DoD**: fixtures covering legal route snippets (UI/API/hybrid), illegal jump rejection, stale downgrade writing `stale` statuses; wired into pre-commit hook from 0.3.
- [ ] **1.4** `render_md.py` deterministic. **DoD**: two runs byte-identical (SHA-256 compared in test); golden output fixture committed.
- [ ] **1.5** `export_xmind.py` (pin XMind ZEN-family zip layout; fix ZIP entry timestamps + doc properties). **DoD**: output opens/parses (zip→content.json structure check) for fixture ≥2 modules; **two runs produce identical SHA-256**; filename versioning `<N>` increments per GLOSSARY.
- [ ] **1.6** `export_xlsx.py` (same timestamp fixing). **DoD**: openpyxl round-trip shows required columns populated; two runs identical bytes.
- [ ] **1.7** `check_coverage.py` — referential integrity always (ids exist, unique per scope, rows resolve) + tier modes `--tier r-t|t-c|c-auto|auto` honoring `testable`/`automation_required`/exemptions-with-reasons. **DoD**: gap fixture fails listing orphan/gap ids with tier-aware message; fully-covered fixture passes; exemption honored only with reason.
- [ ] **1.8** `check_api_coverage.py`. **DoD**: endpoint missing negative/edge fails w/ operation_id listed; `out_of_scope`+reason passes; missing reason fails.
- [ ] **1.9** `check_db_readonly.py` (AST token scan, unified denylist incl. MERGE/REPLACE/UPSERT/CALL/EXEC/COPY, `# db-write-ok` escape hatch) + CI config snippet scanning `automation/**`+`shared/assertions/**` for raw DB-driver imports. **DoD**: pass/fail fixtures per behavior; driver-import fixture caught.
- [ ] **1.10** `check_pom_boundary.py` both directions: locator-API calls in `*/tests/**` AND assert/expect inside pages/components/screens (covers page.click(".sel"), fill("#id",…) forms). **DoD**: four-way fixture matrix (clean/dirty per direction) verified.
- [ ] **1.11** `check_test_markers.py` markers-present & path/marker consistency. **DoD**: missing-marker and mismatched-module fixtures fail; correct sample passes.
- [ ] **1.12** `check_api_models.py` client-method↔model pairing, no raw dict returns. **DoD**: dict-returning-client fixture fails; typed client passes.
- [ ] **1.13** `check_secrets.py` credential-pattern scan over trackable text incl. `00-raw` text dumps. **DoD**: seeded patterns (Bearer/JWT/AKIA-style/DSN-password) caught; clean fixtures pass.
- [ ] **1.14** `check_layering.py` import scan per Architecture §3 table (Python dirs only) + AST path-literal scan blocking `open()/Path()` reads of `iterations/` inside `automation/`. **DoD**: forbidden-edge fixtures (automation→iterations, plugins→skills internals, shared→scripts) each fail; clean skeleton passes; process-rule grep for skills wired as advisory warning.
- [ ] **1.15** Wire everything: pre-commit config finalized; `.github/workflows/ci.yml` static-checks job; commit hand-written sample iteration `iterations/test-fixture-001` as permanent script-test fixture (documented as fixture, exempt from normal cleanup). **DoD**: pre-commit + CI green on skeleton; both RED after intentionally breaking any 1.1–1.14 fixture (smoke-tested then reverted).

## Phase 2 — Plugin Layer Skeleton

- [ ] **2.1** `plugins/_interface/contract.md`: fetch() → disk-persisted envelope validated against source-payload schemas; conversion responsibility = M1/M4; credentials/timeouts/private-network denial/structured error rules (DATA_MODEL §10). **DoD**: human sign-off.
- [ ] **2.2** Two payload schemas + registry entries. **DoD**: schema fixture pairs validate/reject.
- [ ] **2.3** `run_plugin.py`: resolve registry → execute plugin path OR write-persist then validate; unknown-name error path. **DoD**: `run_plugin.py nonexistent ref` exits non-zero with actionable message; persistence-before-validation order covered by a test; envelope lands in `iterations/<id>/00-raw/source-payload.yaml`.
- [ ] **2.4** Placeholder READMEs for requirement/api sources. **DoD**: committed, referenced from AGENTS.md.

## Phase 3 — Core Skill: `test-design`

- [ ] **3.1** `SKILL.md` (authoring template: engineering/CODING_STANDARDS §Skill Authoring Conventions; version frontmatter; confirmation-persistence rules; hash-gating) + schema placements reused; symlink in `.claude/skills/`. **DoD**: human sign-off; `readlink` resolves.
- [ ] **3.2 [manual gate]** Dry run stage 1 on realistic raw input. **DoD**: `requirements.yaml` w/ ambiguities; ≤3-question rounds w/ recommendations observed; user resolution → `clarified`; **explicit accept appends approval record to iteration.yaml** (artifact_sha256 matches); validator green.
- [ ] **3.3 [manual gate]** Stage 2. **DoD**: `test_points.yaml`; coverage tier r-t green on accepted requirements (exemptions carry reasons); user accepts (record appended).
- [ ] **3.4 [manual gate]** Stage 3 + export. **DoD**: cases validated (`module:` tag exactly one, `test_point_ids` cited), t-c tier green, `.xmind` produced via script & parses; agent surfaced export path and paused before invoking generation.
- [ ] **3.5** Idempotency proof: rerun stages on unchanged inputs. **DoD**: hash-gated no-op → `git status` clean without force flags.

## Phase 4 — Skill: `api-test-design`

- [ ] **4.1** SKILL.md + symlink (pattern as 3.1). 
- [ ] **4.2 [manual gate]** Spec normalization from real source. **DoD**: `api/spec.normalized.yaml` passes api_spec schema; module tags valid; out_of_scope endpoints have reasons.
- [ ] **4.3 [manual gate]** Case generation + export. **DoD**: `api/cases.yaml` passes; `check_api_coverage.py` green; xlsx parsed w/ populated columns; two-export byte-identity holds.

## Phase 5 — Target-App Harness, Web Automation + Self-Debug

_5.0 exists because Phase 3 DoDs in v1.0 depended on an app that stood up only in Phase 9 — corrected order._

- [ ] **5.0.1** Target-app lockfile (`target-app/medusa.lock.yaml` pinning backend/storefront/postgres/redis/node per ADR-002) + compose. **DoD**: `target_app_up.py` brings stack healthy; healthcheck green twice consecutively; `down` leaves clean slate.
- [ ] **5.0.2** Seed + reset scripts (Admin-API based, idempotent keys from env name): region/currency, product+inventory, shipping option, manual payment provider, customer, discount code. **DoD**: reset run twice converges (entity ids stable); seeded discount total computable at runtime; teardown-after-failure verified.
- [ ] **5.0.3** Write `knowledge/target-app-notes/medusa.md` (versions, real routes, auth model store-vs-admin, locator strategy, seeded-entity reference table). **DoD**: human review; routes/seed values actually match running instance (spot-check curls recorded).
- [ ] **5.1** `shared/config/settings.py` (precedence CLI>TEST_ENV>local, empty-YAML guard, optional auth/db), root `automation/conftest.py` (strict markers, TEST_ENV=prod read-only collection gate), worker-scoped fixtures pattern. **DoD**: guest-flow config loads w/o auth/db blocks; empty yaml safe; prod-gate deselect verified by a local PROD-flagged dry pytest run; trivial handwritten smoke test passes against harness.
- [ ] **5.2** `shared/db/readonly_client.py` (+ statement-head gate) + unit tests. **DoD**: read statements pass; write/multi-statement blocked; wrapper invoked by a sample db assertion helper.
- [ ] **5.3** Both skills' SKILL.md (web generation + self-debug-runner) + symlinks; `scripts/self_debug_helper.py` bookkeeping (budget counter, attempt log append, diff capture refs). **DoD**: sign-offs; helper records attempts[] conformant to run_summary schema.
- [ ] **5.4 [manual gate]** Generate against Phase 3 cases. **DoD**: POM objects + tests land per module; boundary/markers/layering/model checks pass; traceability upserted with nodeids; c-auto tier green; rerun on unchanged input is no-op.
- [ ] **5.5 [manual gate]** Self-debug proof trio: (a) realistic repairable break → passed within budget w/ attempts history; (b) unfixable stub → clean budget_exceeded diagnosis; (c) seeded product-behavior mismatch → escalated immediately, final diffs touch zero frozen scope. **DoD**: transcripts show zero mid-loop user contact in all three; third case ends escalated w/o remaining-budget consumption.

## Phase 6 — Skill: `api-automation-generation`

- [ ] **6.1** SKILL.md + symlink.
- [ ] **6.2 [manual gate]** Codegen from Phase 4 cases + HAR variant routed through normalization. **DoD**: clients/models/tests generated; `check_api_models.py` green; loop reaches terminal states per 5.5 standard; tier gates hold.

## Phase 7 — CI/CD Wiring

- [ ] **7.1** `regression.yml` e2e per ARCHITECTURE §8 CI shape (service containers, harness lifecycle, secret→env.ci.yaml assembly, artifact upload, notify under always()+continue-on-error, target-down). **DoD**: PR against release containing generated suites goes green incl. e2e; forced-fail scenario notifies without blocking sibling steps.
- [ ] **7.2** Notifier adapters + dispatcher + `notify.py` wrapper. **DoD**: one real channel receives summary; invalid-webhook second channel logs failure without blocking first or job.
- [ ] **7.3** Jenkinsfile mirror. **DoD**: runs on sandbox Jenkins OR explicitly documented unverified.
- [ ] **7.4** Coverage-tier enforcement wired to PR context (changed iterations only; merged-level tiers demand full chain). **DoD**: in-progress draft iteration PR isn't killed by unmet higher tiers; completed iteration PR fails correctly when a required automation link is deleted.

## Phase 8 — Knowledge & Skill Self-Optimization

- [ ] **8.1** Seed knowledge files with real lessons from Phases 3–7 (frontmatter tags/date/source per GLOSSARY-style conventions; trigger per PRD M12). **DoD**: ≥1 genuine entry per file, sourced from build-out events.
- [ ] **8.2** `skill-self-optimizer/SKILL.md`: **nine-step** workflow identify→summarize→propose→confirm→apply→verify→commit→push→resume (fixes v1.0's miscounted "10-step"); threshold ≥2 distinct iterations or ≥3 occurrences; pushes restricted to current iteration branch; versions/<prev>.md snapshot + frontmatter bump before apply. **DoD [manual gate]**: seeded recurring flaw produces proposed diff shown BEFORE changes; application only after explicit confirm; rollback file exists.

## Phase 9 — First Real Iterations (v1 Exit)

- [ ] **9.1 [manual gate]** Fresh harness bring-up + env.local config. **DoD**: healthchecks green; M8 approval record present.
- [ ] **9.2 [manual gate]** UI-led iteration end-to-end (guest checkout w/ discount) → merged. **DoD**: `iteration.yaml.state=merged`; approvals[] reconstruct acceptance solely from directory contents; PR green incl. e2e; notification fired; **attempts[] diff review confirms no frozen-scope patches**.
- [ ] **9.3 [manual gate]** API-led iteration (order totals) same bar. **DoD**: same checks, exercising api skills as primary path.
- [ ] **9.4** Retrospective corrections to AGENTS.md/knowledge/docs. **DoD**: ≥1 concrete correction committed & referenced from the merge PR description.
- [ ] **9.5** Final v1 acceptance sweep vs PRD §7 checklist. **DoD**: each of the five criteria evidenced (links to runs/PRs/approvals).

---

## Deferred (post-v1 — do not start before Phase 9 sign-off)

Mobile (Appium) & mini-program (Minium) generation skills · real plugin connectors (one requirement-source + one api-source first) · Locust script generation · skills-template extraction & sync tooling (ADR-003) · `knowledge/` categorization/scoring · global RTM aggregation · bandit/container hardening of generated-code execution (tracked in RISKS_AND_KNOWN_ISSUES).
