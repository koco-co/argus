# Changelog

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
