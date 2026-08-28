# 项目接续入口 / Agent Brief

核对日期：2026-08-28

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）当前 **Step 0 阻塞；Phase 2 的 2.1 契约草案已提交，等待人工签收**。ROADMAP 已勾选 0.1–0.8 与 1.1–1.18；0.9 按既有安排延后至 7.5，尚未完成。Phase 1 的 schema、注册表、守卫脚本、唯一写入者、确定性导出、真实 pre-commit 钩子及 CI 接线已有实现（不再是桩）。历史台账记录 227 pytest 全绿；本轮未重跑该测试套件，但已通过 GitHub API 核实 Phase 1 提交 `1dd3d05` 的 [Actions static-checks 成功记录](https://github.com/koco-co/argus/actions/runs/33145443151)。2.1 草案提交为 `c0212c2`，ROADMAP 2.1 未勾选，不得开始 2.2。

2026-08-28 本轮真实自检：Docker daemon、Compose、uv、Python 3.12、项目 Playwright Chromium 实际启动、GitHub 远程读取与 Actions 配置读取均成功；当前账号具备仓库 ADMIN 权限。**缺少真实通知 webhook**：`config/notify.yaml` 不存在，通知环境变量为空，仓库 Actions Secrets 与 Environments 均为空，因此未发送通知，Step 0 未通过。完整命令、输出及证据边界见 [Step 0 自检与阻塞记录](./status/STEP0_CHECK_2026-08-28.md)。

规范文档仍以 v1.6 基线为权威。本轮用户明确禁止以 mock/本地单测替代真实依赖验收，覆盖历史“通知降级”许可；历史记录保留但不再作为当前验收依据。本仓库直接施工、每任务 conventional commit、每完成一个 Phase push 一次；人工确认点逐个等待明确确认，不从总目标推断授权。

运行模型要求（非约束性建议）：驱动会话的模型应具备可靠的代码理解、AST 级结构与测试框架知识（参考 NIST Agent Evaluation 的任务能力框架）；Roadmap 5.5 的四个自调试证明用例可直接用作模型验收基准。

## 已完成与下一步

- 已完成：v1.0–v1.6 文档基线（详见 [CHANGELOG](./status/CHANGELOG.md)）；2026-08-27 Phase 0 施工与验收；2026-08-28 Phase 0 关闭（0.6 签收 + 决策留痕）。
- 已完成：Phase 1（1.1–1.18）全部任务按 DoD 完成。要点：全部 DATA_MODEL schema + fixture 对（1.1，含 rfc3339-validator 规格缺陷修复）；registry 十项绑定 + validate_schema/validate_iteration（1.2/1.3，状态机/审批/staleness/attempt 不变量）；render_md/export_xmind/export_xlsx 确定性渲染（1.4–1.6，字节可复现）；五层 coverage 门禁 + api 覆盖 + 六个防御性 checker（1.7–1.14）；patch-scope 与期望语义检查（1.15/1.15a）；三唯一写入者（1.15b）；pre-commit 四钩子真实施行 + ci.yml static-checks + 样本迭代 test-fixture-001（1.16，RED 冒烟验证）；prod-scope 审计与 orphan 反向闭包（1.17/1.18）；227 pytest 全绿。
- 需注意：历史审查记录已消化并按所有者指示删除；被否决的评审建议留痕于 [RISKS_AND_KNOWN_ISSUES](./status/RISKS_AND_KNOWN_ISSUES.md)，不得作为新需求重新引入。
- 下一步（当前停止）：用户将真实通知 webhook 放入被 gitignore 的 `config/notify.yaml`，并提供测试通知的接收渠道信息；不要把密钥写入聊天或受版本控制文件。重新验证真实渠道可用后才能解除 Step 0 阻塞。`env.local.yaml`/`env.ci.yaml` 也尚不存在，属于后续 M8/CI 配置与确认范围，本轮未伪造。
- 随后的任务边界：向用户呈现 [2.1 契约草案](../../plugins/_interface/contract.md) 与提交 `c0212c2` 的 diff，取得明确 human sign-off 后才可标记 2.1 完成；不能直接进入 2.2。后续继续按 ROADMAP 顺序，每项先验证 DoD，再更新台账与勾选状态。
- 本轮仅修正接续状态与记录自检证据；未改实现代码、未勾选任务、未写 `approvals[]`/`state`/`events[]`、未启动靶应用或真实迭代、未 push（Phase 2 未完成）。

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
