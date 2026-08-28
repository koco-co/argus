# Changelog

- 修复批准门禁只匹配 `stage/action`、未核对实际产物的问题：`validate_iteration.py` 现在以该阶段最后一条决定为准，并对 requirements/test-points/exemptions 强制校验当前文件 SHA-256；新增摘要不匹配、后续拒绝、产物缺失回归，永久测试夹具通过唯一批准写入器校正。框架全量回归增至 401 项。

## 2026-08-28 — Phase 5 靶场、环境门禁与只读防线落地

- 补齐数据库能力边界：靶场迁移后幂等创建 `argus_readonly`，仅授予全表 SELECT，并用 `default_transaction_read_only` 和实际建表拒绝探针双重验证；宿主机只通过 `127.0.0.1:15432` 访问。`settings.py assemble` 在注入数据库 DSN 时保留机械可识别的只读声明，真实 UI/API 本地配置检查均通过且文件权限为 `0600`。
- 根据 Actions 原始日志修复两个脚本路径入口：`notify.py` 与 `record_approval.py` 现在能在 `python scripts/<name>.py` 形态导入仓库根包；通知配置缺失时明确记录零渠道而非 traceback。CLI 子进程回归覆盖两种入口，并验证飞书、钉钉、企业微信与 SMTP 的渠道信封和业务错误；真实外部频道送达仍保持未验收。
- 修复 CI 通知事实源：本轮没有 JUnit 时不再选择历史 iteration 摘要，改发当前 job 状态；鉴于 GitHub runner 实测把 `job.status` 展开为空，工作流改用 `failure()`/`cancelled()` 推导非空状态，CLI 同时拒绝空状态，防止“通知步骤通过但消息状态为空”的假阳性。
- 为组合 UI/API 执行增加可选 `api_base_url` 与 `ARGUS_API_BASE_URL`，生成 API 夹具不再硬编码 Medusa 后端地址；配置校验、CI 注入和文档示例同步覆盖。
- 完成 Roadmap 7.4 的 PR 上下文覆盖路由：`--changed-base` 只选择变更 iteration，自动化、共享代码或覆盖工具变化会检查全部历史链，删除 iteration 不得静默跳过；CI 完整拉取历史并传入 base SHA。框架全量回归增至 396 项。
- 为 Roadmap 7.1 增加只在 `workflow_dispatch` 暴露的对抗验收场景：static-checks 可强制进入失败通知分支，e2e 可稳定持续失败或仅首轮失败；常规 PR/定时运行始终为 normal。本地已证明退出序列 `1` 与 `1→0`，框架全量回归增至 398 项，远端调度证据将在提交后执行。

- 固定并容器化 Medusa 2.19.0 开源靶场，提供 build/up/seed/reset/healthcheck/canary/down 生命周期；Admin API 种子覆盖区域与货币、商品库存、配送、手工支付、客户、促销、publishable key，并以私有运行时文件保存凭据。
- 两次 reset 的种子状态字节一致；实时金丝雀验证 EUR 10.00、ARGUS10 10% 与 EUR 9.00 的派生关系，故意破坏价格时按预期失败；完整 down 后未残留 Argus 容器、网络或卷，重新全新启动通过。
- 新增 `settings.py` 的 CLI/TEST_ENV/local 优先级、空 YAML 防护、CI 环境变量注入、`check`/`assemble` 命令，以及 `record_approval(stage=environment)` 的强制前置检查；审批摘要继续只记录脱敏结构。
- 根 conftest 在 PROD 环境机械剔除非 `read_only` 用例，并以每个 xdist worker 独立 HTTP 会话和命名空间隔离状态；真实 harness 模块连续三轮 `pytest -n 2` 通过，PROD dry collect 显示 4/5 收集、1 项非只读探针被剔除。
- 新增运行时 `ReadOnlyDBClient`：语句头白名单、多语句阻断、WITH/EXPLAIN 的 DML/ANALYZE 扫描和共享数据库断言。框架全量测试增至 331 项通过，Ruff、Pyright、DB/marker/orphan 静态门禁通过；这些证据不替代后续生成迭代与最终 UI/API E2E 验收。
- 新增 M9 故障分类器与唯一证据记录器：run 目录不可覆盖、attempt 连续编号、预算计算、diff 引用解析、终态 Schema 校验、恢复检查点强制先验验证组合、patch-scope 调用及 AST import closure 受影响模块选择均已机械测试；升级类证据不能被细分为可修复类。
- 新增钉钉、飞书、企业微信与 SMTP 通知适配器及统一 dispatcher；每个渠道独立按 1/2/4 秒退避重试，失败只记录不阻断兄弟渠道或测试终态；`notify.py --summary auto` 从 append-only run 证据树解析最新摘要，并支持 `flaky-suspect` 分类。
- `self_debug_helper.py record-ci` 将 JUnit 绿/红结果写成唯一一条 `scope=full` attempt；报告归档拒绝覆盖既有 run 证据。真实外部渠道送达仍须在 7.2 DoD 单独验收，未用 mock 代替。
- 新增 SHA 固定、最小权限、并发取消和超时约束的 `regression.yml`：release PR、自动化/迭代变更、手工与每周调度进入 Compose-only E2E；失败只自动复跑一次，重跑转绿标记 `flaky-suspect`；报告与通知使用 `always()`，靶场始终清理。Dependabot 每月更新 Actions/Python 依赖。
- 新增 `finalize_merge.py`，只允许从 `accepted` 写入带 40 位真实 merge SHA 与正 PR number 的 `merged` 事件，并可仅在 `release` 分支创建 Emoji Conventional Commit；实际合并验收仍留在 7.6/9.2/9.3，未预写虚假 merge 事实。
- 用本轮真实构建证据初始化 M12 知识：Medusa 容器 PostgreSQL SSL、SSR 内外 URL 分离、Skill 根目录命令路径和种子 oracle 反事实金丝雀；每条均含 tags/date/source，专项测试防止空来源和重复标题。
- 在 GitHub 创建 `release` 并启用 strict `static-checks`/`e2e`、至少一名人工批准、last-push approval、管理员约束、线性历史及禁止强推/删除；真实直接推送返回 GH006 并被拒绝，证据记录于 `BRANCH_PROTECTION_2026-08-28.md`。

## 2026-08-28 — 完整交付 Goal 与 Phase 2 运行器实现

- 按用户最新指令重设原生 Goal：持续实现全部剩余 v1 需求，以真实开源靶项目的完整 Web/API 自动化验收作为成功终点，不再沿用旧 Goal 在 2.1 处停止的开发安排。没有补造签收、审批或执行证据。
- 实现 `scripts/run_plugin.py`：严格注册表解析、受限子进程调用、现成信封导入、先落盘后统一校验、保留失败载荷、错误变体非零退出、同内容重入和拒绝覆盖；增加凭据过滤、非公网 URL 预检、输入/解压大小限制和超时失败处理。v1 注册表保持零真实连接器。
- 补齐两类来源失败/互斥 fixture、注册表路径验证、运行器集成测试、来源目录 README 和 AGENTS 引用。Schema 单类非法但另一类合法的样本按联合注册绑定正确接受，不混淆单 Schema 与联合路径验证。
- Ruff、Pyright 通过；框架测试 267 passed；未知插件真实 CLI 退出 1；差异检查通过。这些是静态与框架集成证据，不是靶应用或 Web/API 最终验收。
- 本轮尚未提交或 push；保留原有未提交修订及临时文件删除。2.4 的提交 DoD 尚未完成。

## 2026-08-28 — 2.1 契约签收材料修订（待用户确认）

- `plugins/_interface/contract.md` 改为中文说明，保留待签收状态；修正 DATA_MODEL §10 的错误相对路径并补充 ADR-006 链接。机器契约继续由 DATA_MODEL §10 裁决，先落盘后校验、M1/M4 转换职责、安全规则和零真实连接器范围不变。
- 现有来源载荷测试 5 项通过，文档 Schema/仓库结构测试 23 项通过；契约链接及差异检查通过。未将这些检查当作 human sign-off、运行器行为验证或真实连接器验收。
- 已核实应用 Goal 使用新版规则；保留进入本轮时已有的两个临时文档删除，不恢复或提交它们。2.1 尚未勾选，当前修订待签收后再按任务提交。

## 2026-08-28 — 按用户要求调整 Goal 的阻塞判断与汇总时机

- 用户明确要求“不阻塞主流程的，在任务结束后通知”，并要求中文注释/备注。保存完整 [Goal 修订提示词](./GOAL_PROMPT.md)，同步 AGENT_BRIEF 和环境自检入口；旧自检结果保留为历史证据。
- 裁决：最新用户执行指令覆盖旧 Goal 的“任意缺项即停”。结合 ROADMAP 5.5 明确 Phase 7 前执行终态在会话内呈现，webhook 归为后续阶段待办；到 Phase 7 首个真实通知 DoD 时仍须真实配置和验证。未修改 PRD/ROADMAP 的 DoD、任务顺序、人工签收或最终验收标准，未将 mock 当成真实验收。
- 当前应用 Goal 工具没有目标正文编辑参数，Computer Use 操作 Codex 界面被安全策略禁止；原生 Goal 正文尚未替换。没有手改应用内部存储、重建目标或伪报目标完成；仓库中的修订文本和当前用户补充指令可供后续接续。

## 2026-08-28 — Step 0 recheck blocked; recovery ledger corrected

- Resumed from ROADMAP + AGENT_BRIEF and the current checkout, not a fresh scaffold. ROADMAP records 0.1–0.8 and Phase 1 complete, with 0.9 deferred to 7.5. Existing commit `c0212c2` contains the 2.1 contract draft; human sign-off remains pending. Corrected the stale “Phase 2 not started” / “local hooks are stubs” descriptions in AGENT_BRIEF without changing any task checkbox or approval/event artifact.
- Current user instruction requires real dependencies and forbids mock substitution for acceptance. It supersedes the historical notification fallback recorded below; that history remains intact but is not current authorization to lower M11/7.2 or final acceptance. No PRD, DATA_MODEL, architecture, or DoD contract was changed.
- Live checks confirmed Docker/Compose, uv/Python 3.12, actual project Chromium startup, GitHub repository/admin access, enabled Actions, and the successful Phase 1 static-checks run. A real webhook is unavailable in the checked local/repository configuration, so Step 0 is blocked and implementation stops. Commands, safe outputs, scope limits, and user actions are recorded in [STEP0_CHECK_2026-08-28](./STEP0_CHECK_2026-08-28.md).

## 2026-08-28 — Phase 1 task 1.1 implemented; spec defect fixed (rfc3339-validator)

- **1.1** All DATA_MODEL schemas authored at their owning placements (requirements/test_points/functional_cases under `.agents/skills/functional-test-design/schemas/`; api_spec/api_cases under `.agents/skills/api-test-design/schemas/`; exemptions/traceability/run_summary under `scripts/schemas/`; two source payloads under `plugins/_interface/schemas/`). Every `generated_from` definition incorporates the documented optional `inputs[]` sibling (DATA_MODEL intro). Fixture pairs committed under `scripts/tests/fixtures/schemas/` covering the DoD list (missing required, bad enum/pattern, unresolved-ambiguity at `accepted`, missing `generated_from` at terminal states, invalid expectation kind, API case without `requirement_ids`, vacuous-conditional regressions, combinator preservation + `$ref` patterns, mutual-exclusion payloads, malformed `date-time`); `test_docs_schemas.py` extracts and parses every fenced JSON Schema block in DATA_MODEL (count pinned at 10).
- **Spec defect fix (minimal revision, recorded)**: ENVIRONMENT_SETUP's closed core-dependency list could not satisfy DATA_MODEL's mandate "validators run with a FormatChecker enabled so `format: date-time` rejects malformed strings" — jsonschema's date-time checker is a silent no-op without `rfc3339-validator`. Added `rfc3339-validator>=0.1.4` to core deps (additive; proven necessary by the failing malformed-date-time fixture). Update of the dependency list in ENVIRONMENT_SETUP follows below with the next doc touch.


## 2026-08-28 — Phase 0 closed; owner decisions recorded

- **0.6 human sign-off given** (manual gate satisfied by explicit user confirmation; no `approvals[]` artifact is written — that namespace belongs to iteration artifacts via `record_approval.py`, so the gate is recorded here and in AGENT_BRIEF).
- **Repo placement confirmed**: build directly in this repo (owner-confirmed; the `<target-app>-automation` split stays a post-v1 mechanical option, see ARCHITECTURE §2 future-split boundary).
- **Notification DoD fallback authorized** (owner decision): M11/7.2's "one real channel receives summary" is executed as dispatcher unit tests + local verification with the deviation recorded; a real webhook upgrade path remains open. Recorded because the fallback is an acceptance-level authorization, not an implementation choice.
- **Push policy**: one push per completed Phase (owner decision); Phase 0 pushed at close.
- Phase 0 → Phase 1 transition: ROADMAP 0.6 checkbox flipped; Phase 1 (1.1–1.18) starts next per the one-task-at-a-time discipline.


## 2026-08-27 — Phase 0 infrastructure implemented & accepted (docs v1.6 → +code)

First product code in the repo. ROADMAP Phase 0 executed task-by-task per its own discipline; every claimed DoD was mechanically verified in the same session. Scope decision delegated to the session by the owner's instruction ("自己设定一个goal，明确目标边界"): build directly in this repo (the `<target-app>-automation` alternative remains available post-hoc — the ARCHITECTURE §2 tree is relative).

Implemented (Roadmap tasks):
- **0.1** `uv python pin 3.12` → `.python-version`; fresh `uv sync` exits 0 on CPython 3.12.12.
- **0.2** `pyproject.toml`: core deps exactly per spec; `[dependency-groups]` dev(ruff/pyright/pre-commit) + optional mobile/perf; pytest markers `module/case_id/iteration` with `--strict-markers`; ruff `E,F,I,UP,B,SIM` ll=100; pyright basic. Verified: ruff+pyright clean; `appium-python-client`/`locust` not installed by default; `uv.lock` committed; `pytest --collect-only scripts/tests` green with all plugins loading. `docs/` excluded from ruff so formatter churn never touches the spec baseline (caught live during setup).
- **0.3** `.pre-commit-config.yaml`: remote ruff hooks (format check-only — no hook mutates tracked files) + four local hooks at their prescribed entries. Interpretation recorded: the local validator scripts exist as explicit **stubs naming their implementing task (1.2/1.3/1.9/1.13)** so hooks are no-op-clean on the skeleton while the file paths stay final; `check-secrets` scoped to `^iterations/.+/` (keeper files excluded). Verified: `pre-commit install` + `run --all-files` green.
- **0.4** `Makefile` per the ENVIRONMENT_SETUP target table (no `debug` target; module selection by path; `BRANCH` variable passes the branch declaration to `new-iteration`).
- **0.5** `.gitignore` per ADR-012 + ENVIRONMENT_SETUP: env/notify secrets, `reports/**` + keeper re-include, `automation/api/har/**` + keeper, `config/env.ci.yaml`, run-evidence rules (`runs/*/allure-results|logs|traces` ignored; `run-summary.yaml`/patches tracked), 00-raw binary patterns with manifest fallback. Verified: dummy `config/env.local.yaml` invisible to `git status`; `git add reports/` stages both keepers.
- **0.6** Full `AGENTS.md` operating rulebook (confirmation points, sole-writer approval rule, branch routing, reopen protocol, ≤3-question clarification protocol with recommendations, prod read-only rule, toolchain quick reference) + `CLAUDE.md` = `@AGENTS.md`. **Human sign-off pending — the acceptance gate is left to the user; agents must not fabricate approval records.**
- **0.7** `scripts/schemas/iteration.schema.json` (DATA_MODEL §3 verbatim) + `scripts/schema_registry.yaml` (single binding) + `scripts/new_iteration.py` (GLOSSARY id validation, single-in-progress rule, typed-confirmation `--force` resetting only scaffolder-owned paths, post-scaffold validation through the shared registry path with `FormatChecker`). Design decision recorded: the scaffolder creates `iteration.yaml` + directory tree only — artifact YAMLs beyond the iteration aggregate are NOT stubbed because most DATA_MODEL schemas have no schema-valid empty form (`minItems: 1`), and an invalid placeholder would fail Phase 1 gates; owning skills create them at their phase. Validated by 14 pytest cases (expected-tree fixture diff, duplicate/ID/single-in-progress/branch rules, hybrid-branch schema rejection, force flows).
- **0.8** Full ARCHITECTURE §2 skeleton (six skill dirs with schemas/examples/versions, plugins layer, automation module trees, shared/, reports keepers, knowledge files, config examples with read-only-role comment, target-app home, `.github/workflows`), locked by `scripts/tests/test_repo_structure.py` (expected-set + governed-children drift guards).

Not done / deferred: **0.9** branch protection — `release` first materializes at the first iteration PR; protection completes at 7.5 per the task's own cross-reference. **0.6 sign-off** awaits the user.

Acceptance evidence: fresh `git clone` → `make setup` → `make new-iteration ID=2026-08-acceptance-check BRANCH=ui` → `make lint` all green with zero manual steps (the Phase 0 exit condition); `uv run pytest scripts/tests` 43 passed; ruff/pyright clean; `pre-commit run --all-files` green. Environment note (host-specific, not a repo defect): the machine's system proxy breaks TLS to github.com/pypi/CDN intermittently — PyPI and the Playwright CDN need direct connections (`NO_PROXY=pypi.org,files.pythonhosted.org` / cleared proxy env for `playwright install`); recorded here because ENVIRONMENT_SETUP's statuses above were verified under that workaround.


## 2026-08-27 — v1.5 baseline review adoption (v1.5 → v1.6)

Input: external review of the v1.5 tree (20 findings: P0×2 / P1×6 / P2×9 / P3×3). Adjudication table presented and confirmed before editing. Disposition: 10 adopted, 6 lightweight/partial, 4 rejected with recorded rationale.

Adopted:
- **Session-recovery protocol** (P0-1): `self_debug_helper.py` checkpoints resumable state (`attempt_number`, `patched_files[]`, `verification_pending`) into `runs/<run_id>/state.json` at attempt boundaries; a fresh session must consume it — pending verification runs before any new patch decision, budget resumes from the checkpoint. Recovery fixture added to Roadmap 5.3.
- **CI secrets injection rule** (P0-2): secrets travel only via workflow `env:` mapping — never shell args or inline `echo` (the v1.4 skeleton's `echo > env.ci.yaml` replaced with in-process `settings.py assemble --env ci`); `settings.py` gains env-var overrides so most jobs need no secrets file at all.
- Optimizer candidate registry `knowledge/optimization-candidates.yaml` (M12-maintained feed; 8.2 reads candidates from it, threshold counted by the registry).
- OpenAPI projection: `schema_fragment` now legally carries `allOf`/`oneOf`/`anyOf` (previously rejected by `additionalProperties: false` — the review's "already supported" claim was wrong and is corrected in the record), `$ref` flattening capped at depth 5 with `normalization_warnings[]` for degradations, and warning-degraded branches make M7 escalate rather than invent typed models.
- Failure-classification decision tree (element-absent vs element-present mismatch etc.) with fabricated-evidence fixtures in 5.3; Dependabot monthly cadence + immediate security path; weekly-run failure escalation (notify → 2×issue; scheduled runs never gate merges); `<behavior>` naming rule in GLOSSARY + 5.4 check; skill version SemVer semantics + regenerate-old-iterations constraint + recorded merge-evaluation criteria for the four generation skills; non-binding minimum model-capability guidance in AGENT_BRIEF (5.5 quartet as benchmark); RISKS additions #17 (plugin envelope untested, additive-only during v1) and #18 (iterations/ scan cost, archival deferred); iteration_id time prefix marked recommended-not-mandatory.

Rejected with rationale (see RISKS rejected-proposals posture): letting the repair loop edit seed-registry formulas (the formula defines the expected value — self-certifying; wrong formula escalates to the user via reopen, now stated explicitly in PRD §4.7 + CODING_STANDARDS); restructuring `.agents/skills/` + symlinks into an agent-agnostic resolver (symlinks are the documented Claude Code adapter; multi-agent resolver is post-v1, Deferred); structured precondition objects (no mechanical consumer in v1); a `conversation-log.jsonl` subsystem (decision-bearing content is already persisted structurally — PRD §7.4 reworded to reference persisted run evidence instead of the unverifiable "transcripts").

## 2026-08-27 — v1.4 baseline review adoption (v1.4 → v1.5)

Input: external review of the v1.4 snapshot (20 findings: P1×7 / P2×8 / P3×5, no P0). Plan presented and confirmed before editing; every finding re-verified against the working tree first. All 20 dispositioned: 14 adopted, 5 lightweight/partial, 1 sub-item rejected (core/adapter ADR draft stays deferred).

Adopted (P1): `requirements.priority` field (M1 proposes, user confirms at accept, absent ⇒ 2) so M2's priority-1 depth rule is decidable; API-led exemption production via a requirements-mapping sub-stage and new `requirements_mapped` route state (fixes the Phase 9.3 deadlock where the API branch had no legal exemption producer); `scripts/record_event.py` as sole writer of `state` transitions + `events[]` (symmetric with record_approval.py, closes the audit-forgery asymmetry); tiered evidence storage policy ([ADR-012](../architecture/adr/adr-012-evidence-storage-policy.md): run-summary + patch refs in git, allure/logs/traces gitignored/artifact-only, traces added to the redaction boundary); `finalize_merge.py` given a creation task (7.6) and tree entry; `check_orphan_tests.py` reverse closure (collected nodeids must resolve to cases + traceability — makes the no-hand-written-automation acceptance criterion mechanical); seed registry (`shared/testdata/seed-registry.yaml`, 5.0.2 output) with `derived_from.seed` resolution enforced from M6 on.

Adopted (P2/P3): `settings.py check` mode gating the M8 approval; CI flake policy (failed e2e re-runs once → `flaky-suspect` classification via M12 channel) and weekly scheduled full regression against `release` HEAD; `self_debug_helper.py record-ci` as the sole CI summary writer plus a `failed` status in the run_summary enum (single-shot executions had no representable terminal state); directory-tree naming unified (`target_app_*`), missing scripts added, tree declared the single structural authority; stub-return literal heuristic in the POM boundary checker + a fourth self-debug proof case; optimizer golden-artifact regression as a hard 8.2 DoD; AGENT_BRIEF index de-versioned; optional gitleaks pairing noted in 1.13; validation fix-loop budget exhaustion now ends in `blocked(validation_budget_exhausted)` uniformly (M3/M4/M6/M7); `exemptions` added to the iteration artifacts map (optional, additive); acceptance criterion #1 narrowed to "no hand-written automation for iteration cases" with the exempt infrastructure surface listed.

Deferred with records: full flake-quarantine workflow, core-package/project-adapter split (triggers made observable in RISKS #13/#14), per-module asset-ownership model noted as a precondition in ADR-001 before lifting the single-in-progress rule.

## 2026-08-27 — GPT spec review adoption (v1.3 → v1.4)

Input: external GPT review of the v1.2 `spec.zip` snapshot (48 findings, P0×14 / P1×27 / P2×5 / P3×2). Every finding was re-verified against the current v1.3 tree before acting — several were already fixed by the Claude/Grok adoptions, and its headline "Schema 非法 JSON" probe did not reproduce against either snapshot (all fenced blocks parse).

Already satisfied by ≤v1.3 (no change needed): API-led R→A lineage (#3), Hybrid explicitly forbidden in v1 rather than branch-sub-stated (#4), API status/env-enum/tier-count consistency (#14), GitHub Actions as sole CI authority with Jenkins post-v1 (#33), Performance removed from product title (#44), optimizer self-apply guardrails (#35 core concern), Postgres component retention / typed expectations groundwork (#7/#17 partials).

Adopted as documentation-contract changes:
- Schema fixes (DATA_MODEL §5–§10): `out_of_scope` conditional now carries explicit `required` (absent property can no longer vacuously demand a reason); unusable Draft-07 `maxContains` removed, exactly-one-module-tag demoted to semantic enforcement; source-payload envelope gains `schema_version` plus mutually-exclusive success/error variants; run-summary gains terminal-state conditionals (timing/env/scope/attempts required when terminal, escalation required when escalated); `input_sha256` gets hash pattern; schema_fragment preserves `format`; documented dialect rules (defaults are annotations, FormatChecker always on) and `generated_from.inputs[]` extension.
- Per-run evidence layout: `iterations/<id>/runs/<run_id>/` with append-only summary/allure/logs ([ADR-010](../architecture/adr/adr-010-per-run-evidence-directories.md)); global `reports/` demoted to display scratch; CI archives/uploads run dirs.
- Merge lifecycle truthfulness: PR requires `accepted`; `merged` is finalized post-merge onto release with real merge SHA/event via `scripts/finalize_merge.py` ([ADR-011](../architecture/adr/adr-011-post-merge-finalization.md)).
- Roadmap order/DoD repairs: contract bootstrap absorbed into 0.7 (fixes registry used-before-created); 0.3 local hooks activate no-op-clean until their scripts exist; validate_iteration is a pure check with separate `--fix`; nodeid collectability cross-check in 1.7; new 1.17 `check_prod_scope.py`; seed-integrity canary in 5.0.2; WITH/EXPLAIN data-modifying-CTE negatives in 5.2; Phase 7 hardening (SHA-pinned actions, minimal permissions, timeouts/concurrency) reflected in ARCHITECTURE skeletons; 8.2 candidates must cite evidence + minimal eval set; 9.2/9.3 use accepted→post-merge flow.
- Security/audit honesty: prod protection restated as layered defense-in-depth (collection gate + static write-call audit + read-only DB role as true boundary); M8 approvals digest redacted-copy based so approvals cannot double as secret oracles; target-app harness added to canonical directory tree; control-plane note stating v1's no-orchestrator stance; generated suites pinned to synchronous httpx clients; skill frontmatter aligned to Agent Skills convention (`metadata.version`) with per-skill write scope/stages.
- Trace mandatory for failed debug cycles; API cases declare `side_effect` excluded from automatic reruns; clarification protocol allows composable mixed options; M12/plugin content treated as untrusted data.

Rejected/reaffirmed-with-records (see [RISKS_AND_KNOWN_ISSUES](./RISKS_AND_KNOWN_ISSUES.md) #12–16 and the refreshed rejected-proposals table): cryptographic approval receipts, full provenance-graph-per-artifact, forced M3 semantic gate (Spec Kit analogy reconsidered), sqlparse dependency, bandit/container sandbox gate, orchestrator service, multi-project core split, cross-iteration UID model, skill eval-harness baselines — all either superseded-by-lighter-mechanism or deferred with explicit revisit triggers.

## 2026-08-27 — Grok spec review adoption (v1.2 → v1.3)

- Adopted the Grok contract findings: API-led coverage is now R→A→nodeid with `requirement_ids[]`; UI/API branches are explicit; exemptions moved to immutable-source-safe `exemptions.yaml`; accepted artifacts use explicit approval/reopen tooling and stale blocking.
- Added typed functional expectation kinds and seed/rule provenance, stronger self-debug frozen-scope and mechanical failure preclassification, AST import-closure regression, case-aware asset naming/retirement, and one in-progress iteration protection.
- Preserved API parameter/body/response types, referenced OpenAPI components, and replay variables; defined XMind/XLSX semantic export structures, added `ci` to the environment contract, switched CI coverage to `from-iteration`, and made GitHub Actions the sole v1 CI authority.
- Defined exact CI triggers/notifications/source-payload validation, removed M12's time-based trigger, clarified M12 ownership, aligned locator guidance with the target-app notes, and removed Performance from the v1 product title.
- Added [ADR-009](../architecture/adr/adr-009-exemptions-and-accepted-artifact-reopen.md); Jenkins mirror and cross-repo skill reuse remain explicitly post-v1.

## 2026-08-27 — Claude spec review adoption (v1.1 → v1.2)

- Adopted all 16 review findings as documentation-contract changes: fixed and test-planned all embedded JSON Schemas, unified API lifecycle status names, required functional-case preconditions, bounded iteration IDs, and made the coverage model explicitly three tiers with an aggregate `auto` mode.
- Clarified v1 scope: Hybrid iterations are post-v1; iteration validation accepts exactly one UI/API branch. Functional test design is named symmetrically with API test design.
- Added ADR-008 for the deliberate move from shared, order-dependent test data to run-namespaced data and worker-isolated fixtures; added a real parallel-run DoD.
- Added the self-debug patch-scope checker contract, affected-module regression definition, assertion-change review signal, and fixture/CI obligations.
- Defined the shared M12 knowledge-capture contract, made the target-app CI harness Compose-only, and added the Phase 7 branch-protection closure with required checks and human review.
- Path correction: earlier entries describe intermediate documentation layouts; the final canonical live paths are under `docs/spec/`, with ADRs under `docs/spec/architecture/adr/`.

## 2026-08-27 — Documentation consolidation: review adoption & contract completion (v1.0 → v1.1)

- Documentation reorganization (product code not involved; this repository is still documentation-only):
  - Created `docs/DATA_MODEL.md`: complete definitions for all nine machine Schemas (added missing `api_spec`, added the persistence vehicle `iteration` for global state, refactored `traceability` into a sparse row + derived coverage, fixed `requirements` accepted-state validation gap and the dangling reference of `functional_cases`, defined `run_id`/failure classification in run_summary), with an explicit binding table between filenames and Schemas.
  - Updated `docs/Product Requirement Document (PRD).md`: self-debug allowed patch surface/negative list/failure classification/escalation path, branch-aware global state machine + staged coverage gating, audit trail (approvals/source manifest) and stale propagation rules, clarification interaction protocol, rewritten idempotency NFR as input hashing discipline, added v1 acceptance criteria.
  - Updated `docs/Architecture Design Document.md`: data flow vs dependency rules separated (fixing contradiction from §1/§3), directory tree completion (`shared/config`, `notify.example.yaml`, `schema_registry`, harness scripts, etc.), unified DB read-only scan scope, prod mechanical gate, corrected ReadOnlyDBClient leading-keyword allowlist (eliminating false-positive string matching).
  - Rewrote `docs/Task Implementation Roadmap.md`: target app environment advanced to Phase 5 first task (fixed dependency inversion), Phase 1 extended with all gate tasks and fixture repositories, DoDs all made executable (corrected allure package name/openpyxl/pytest filter syntax/remove phantom modules), CI split into static/e2e.
  - Refactored `docs/Implementation Guide.md`: phase numbering removed (mapping table changed to pointing to Roadmap), new target-app harness and test data policy chapter, corrected Medusa walkthrough factual errors, CI skeleton fix.
  - New docs: GLOSSARY/CODING_STANDARDS/TESTING_STRATEGY/ENVIRONMENT_SETUP/RISKS_AND_KNOWN_ISSUES/AGENT_BRIEF and this CHANGELOG.
- Confirmed decisions: ADR-001–006 (`docs/adr/`); ADR-003 supersedes the premature decision of skills-template repo in Implementation Guide v1.0.
- Rejected and archived by record: bandit hard gate/sqlparse replacement/global RTM/numeric SLOs/M3 forced confirmation, etc. — see RISKS_AND_KNOWN_ISSUES "rejected proposals".
- Verification and evidence: cross-document reference check passed (link and path verified at finalization stage); ENVIRONMENT_SETUP command marked "to be implemented" (no product code before running). All content based on: root `审查文档.md` seven model reviews, original four v1.0 documents, market research industry consensus (self-healing must produce human-reviewable changes, does not perform self-modification testing inside CI).

## 2026-08-27 — 文件名对齐规范与审查记录归档（仅文档整理）

- 已实施：按文档职责规范重命名 `Product Requirement Document (PRD).md → PRD.md`、`Architecture Design Document.md → ARCHITECTURE.md`、`Task Implementation Roadmap.md → ROADMAP.md`；根目录 `审查文档.md` 迁入 reviews/model-reviews-2026-08.md（当日消化后，经所有者确认删除）；全库交叉引用同步更新。
- 验证与证据：链接存在性复查见下方校验说明；产物代码无变更。

## 2026-08-27 — 规范文档归位 docs/spec/，审查记录删除（仅文档整理）

- 已实施：12 类规范文档及 adr/ 移入 spec/；AGENT_BRIEF 与 CHANGELOG 留在 docs/ 作为导航与日志；已消化的七模型审查记录经所有者确认删除。
- 验证与证据：全库相对链接逐一探测无失效。

## 2026-08-27 — 按 skill 职责表编排 spec 四域结构，融合并删除两份补充文档（仅文档整理）

- 已实施：spec 内按 `product / architecture / engineering / status` 子目录编排全部 12 类文档，AGENT_BRIEF 迁至 `docs/spec/AGENT_BRIEF.md`，根 AGENTS.md 入口同步更新。`Implementation Guide.md` 内容融入：§2 靶应用 harness/种子策略 → engineering/TESTING_STRATEGY「Target-App Harness & Seed Policy」，§3 Skill 编写模板 → engineering/CODING_STANDARDS「Skill Authoring Conventions」，§5 CI 骨架 → architecture/ARCHITECTURE §8，其余章节此前已由 ADR 与既有文档承接；`Repo structure.md` 的 v2 结构决策记录为 [ADR-007](../architecture/adr/adr-007-repo-layout-redesign.md)。两份源文档随后删除。
- 已确认决策：ADR-007 新增（repo 布局重设计的出处固化）。
- 验证与证据：删除后全库无指向两文件的失效引用（历史条目按记录纪律保留原文）；全库相对链接逐一探测通过。
- 路径说明：本条描述的是归档前的中间目录状态；最终规范目录以 `docs/spec/` 及其子目录为准。
