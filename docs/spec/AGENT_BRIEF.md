# 项目接续入口 / Agent Brief

核对日期：2026-08-29

## 最新执行覆盖：完整交付 Goal

用户最新指令要求持续实现全部剩余需求，只有成功使用框架完成真实开源靶项目的完整 Web/API 自动化代码验收，才能结束 Goal。已重新创建并读取确认原生 Goal 为 active；本页下方较早记录中的“等待 2.1 签收、不得进入 2.2”不再作为本次开发会话的暂停安排。此覆盖不等于伪造产品迭代的审批记录，也不删除框架应具备的确认、唯一写入者和验收审计能力。

当前实现已覆盖六个项目级 Skill、契约与唯一写入者、Medusa Compose 靶场、Web/API 代码生成、M9 自调试证据链、GitHub Actions 双门禁、通知适配器以及受保护分支收口脚本。两类来源连接器仍是 v1 明确排除的 post-v1 插件边界；运行器已经实现信封校验、失败隔离和安全拒绝。

本轮最终机器验证：`make lint` 通过；`uv run pytest scripts/tests -q` 为 **430 passed**；四个生成 Skill 的冻结输入/语义黄金基线通过；`uv run pre-commit run --all-files` 的 6 个钩子通过；正式 UI iteration 的 10/10 真实 Medusa 浏览器用例与正式 API iteration 的 20 个 case（连同既有 fixture 共 22/22）均有本地 run 证据；fresh reset 后完整 Web/API/fixture/靶场套件再通过 **38 passed in 122.71s**。本地 PostgreSQL SELECT-only 角色已真实读取权限并拒绝建表探针。正式 API 证据链位于 `iterations/2026-08-medusa-api-checkout/`，最新已归档 run 为 `run-20260828T182611Z-api3`，执行摘要为 fresh reset 后 22/22 通过，其中 A0018 缺少支付提供者时返回结构化 400。远端 PR #1 的历史 `static-checks` 与 Compose-only `e2e` 证据仍对应提交 `74897fe`（run `33176595798` / `33176595811`）；本地新增提交尚未推送。当前仓库没有实际通知 Secret，因此真实外部送达仍未验收。验收证据见 [ACCEPTANCE_2026-08-28](./status/ACCEPTANCE_2026-08-28.md)。

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）当前已完成所有不依赖外部责任方的 v1 实现与机器验收。针对本任务，用户已明确授予持续代理决策权：对仓库内正式 iteration 工件，agent 在完成 Schema、覆盖、来源和真实行为审查后可通过唯一写入器记录 `action: delegated`，不再反复请求同类确认。该记录如实标明 `actor: agent` 和授权说明，不冒充用户亲自接受。真实通知送达、非作者 PR 批准、受保护分支合并及合并后真实 SHA 仍只能由对应外部事实完成；测试 fixture 只证明框架能力，不冒充这些事实。

2026-08-29 复核：Docker/Compose、uv、Python 3.12、项目 Playwright Chromium 和 GitHub 远程读取均可用；`config/notify.yaml` 仍不存在，`gh secret list` 与 `gh variable list` 均无通知配置，因此没有真实通知证据。历史自检记录可用 `git show 2b61331:docs/spec/status/STEP0_CHECK_2026-08-28.md` 复核；该临时文件的当前工作区删除状态予以保留。本轮没有把适配器单测或零渠道日志标记为真实送达。API iteration 已通过合法 delegated reopen 重建状态链，旧 run 仅作历史记录，不作为本轮终态摘要。

规范文档仍以 v1.6 基线为权威。本轮用户明确禁止以 mock/本地单测替代真实依赖验收，覆盖历史“通知降级”许可；历史记录保留但不再作为当前验收依据。本仓库直接施工、采用 Emoji Conventional Commit 并持续推送；人工确认记录仍只针对具体工件生效，不从总目标推断或补记。

最新用户执行要求：不影响当前任务/DoD 的问题先记台账，任务结束时统一汇总；只有当前依赖缺失、明确人工确认点或安全/授权边界才暂停，不反复检查未变化的非阻塞项。新增或修改的代码注释、文档备注使用中文。本轮通过 `get_goal` 核实原生 Goal 已包含修订规则且处于 active；其中复制进去的“正文尚未替换”前言是过时说明，不影响新版规则生效。临时提示词文件的工作区删除状态予以保留，不重建。

运行模型要求（非约束性建议）：驱动会话的模型应具备可靠的代码理解、AST 级结构与测试框架知识（参考 NIST Agent Evaluation 的任务能力框架）；Roadmap 5.5 的四个自调试证明用例可直接用作模型验收基准。

## 已完成与下一步

- 已完成：v1.0–v1.6 文档基线（详见 [CHANGELOG](./status/CHANGELOG.md)）；2026-08-27 Phase 0 施工与验收；2026-08-28 Phase 0 关闭（0.6 签收 + 决策留痕）。
- 已完成：Phase 1（1.1–1.18）全部任务按 DoD 完成。要点：全部 DATA_MODEL schema + fixture 对（1.1，含 rfc3339-validator 规格缺陷修复）；registry 十项绑定 + validate_schema/validate_iteration（1.2/1.3，状态机/审批/staleness/attempt 不变量）；render_md/export_xmind/export_xlsx 确定性渲染（1.4–1.6，字节可复现）；五层 coverage 门禁 + api 覆盖 + 六个防御性 checker（1.7–1.14）；patch-scope 与期望语义检查（1.15/1.15a）；三唯一写入者（1.15b）；pre-commit 四钩子真实施行 + ci.yml static-checks + 样本迭代 test-fixture-001（1.16，RED 冒烟验证）；prod-scope 审计与 orphan 反向闭包（1.17/1.18）；227 pytest 全绿。
- 需注意：历史审查记录已消化并按所有者指示删除；被否决的评审建议留痕于 [RISKS_AND_KNOWN_ISSUES](./status/RISKS_AND_KNOWN_ISSUES.md)，不得作为新需求重新引入。
- Phase 2 已完成：插件契约由用户明确签收；来源信封 Schema、运行器、失败变体、目录说明和 AGENTS 引用均已有代码、测试与提交证据。真实连接器仍按 PRD §8 保留到 post-v1。
- 已完成：六个项目级 Skill、确定性辅助脚本、Medusa 靶场、Web/API 生成、M9 四类证明、移动端视觉证据、双 CI 门禁、周回归连续失败升级、通知隔离重试与合并收口实现。
- 外部待办：提供 `config/notify.yaml` 或 CI Secret 后执行真实频道送达；适配器和 CI `always()` 调用已验证，但 9.2/9.3 的外部送达不豁免。
- 已处理的内部门禁：正式 UI/API iteration 的需求、测试点、豁免和环境，在持续授权下由 agent 逐项审查并通过 `record_approval.py` 以 `delegated` 落账；API 额外持久化 `delegation` 的 basis 摘要、scope 和有效期，旧终态经 `reopen_iteration.py` 重开后重新执行并接受；不得把 fixture 或本次总目标确认冒充为工件批准。
- 外部待办：由非 PR 作者批准并合并 PR #1，随后用真实 merge SHA 执行 `finalize_merge.py`。当前仓库只有作者本人可审查，无法自批。
- 本次持续授权只覆盖仓库内可审计的需求/测试设计、环境和终态接受流程；这些记录仍须在对应产物生成后由唯一写入者脚本落账。通知送达、非作者审查、合并和真实 SHA 不在代理授权范围内。

## 文档索引

| 职责 | 实际位置 | 状态 |
| --- | --- | --- |
| 接续 AGENT_BRIEF | 本页 | 已建立 |
| 需求 PRD | [product/PRD.md](./product/PRD.md) | 已建立 |
| 路线 ROADMAP | [product/ROADMAP.md](./product/ROADMAP.md) | 已建立 |
| 术语 GLOSSARY | [product/GLOSSARY.md](./product/GLOSSARY.md) | 已建立 |
| 架构 ARCHITECTURE | [architecture/ARCHITECTURE.md](./architecture/ARCHITECTURE.md) | 已建立 |
| 数据 DATA_MODEL | [architecture/DATA_MODEL.md](./architecture/DATA_MODEL.md) | 已建立（Schema 唯一权威） |
| 决策 ADR | [architecture/adr/](./architecture/adr/) （adr-001…012） | 已建立 |
| 编码 CODING_STANDARDS | [engineering/CODING_STANDARDS.md](./engineering/CODING_STANDARDS.md) | 已建立 |
| 测试 TESTING_STRATEGY | [engineering/TESTING_STRATEGY.md](./engineering/TESTING_STRATEGY.md) | 已建立（含靶应用 harness/种子策略） |
| 环境 ENVIRONMENT_SETUP | [engineering/ENVIRONMENT_SETUP.md](./engineering/ENVIRONMENT_SETUP.md) | 已建立；区分历史运行状态与本轮 Step 0 证据，后续命令不得推定已验收 |
| 变更 CHANGELOG | [status/CHANGELOG.md](./status/CHANGELOG.md) | 已建立 |
| 风险 RISKS_AND_KNOWN_ISSUES | [status/RISKS_AND_KNOWN_ISSUES.md](./status/RISKS_AND_KNOWN_ISSUES.md) | 已建立 |

配套阅读顺序建议：PRD → GLOSSARY → ARCHITECTURE → DATA_MODEL → ROADMAP；工程实现前必读 engineering 三篇与相关 ADR。
