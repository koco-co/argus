# 项目接续入口 / Agent Brief

核对日期：2026-08-27

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）处于 **Phase 0 基础设施已建成、Phase 1 待启动**阶段。2026-08-27 完成 ROADMAP Phase 0（任务 0.1–0.5、0.7、0.8 已按 DoD 验证）：uv + Python 3.12 工具链、pyproject/Makefile/.gitignore、pre-commit 守卫（远程 ruff 强制，四个本地校验钩子为指向 1.2/1.3/1.9/1.13 的显式桩）、ARCHITECTURE §2 目录骨架、`iteration.schema.json`（DATA_MODEL §3 逐字）+ schema registry + `scripts/new_iteration.py`（43 个 pytest 全绿，含全新 clone 退出条件验收）。规范文档 v1.6 契约闭环维持不变。范围决策留痕：经会话自治决策**在本仓库直接施工**（AGENT_BRIEF 原留待用户确认的备选"新建 `<target-app>-automation` 仓库"仍可后置执行，架构树为相对布局，机械搬移即可）。

运行模型要求（非约束性建议）：驱动会话的模型应具备可靠的代码理解、AST 级结构与测试框架知识（参考 NIST Agent Evaluation 的任务能力框架）；Roadmap 5.5 的四个自调试证明用例可直接用作模型验收基准。

## 已完成与下一步

- 已完成：v1.0–v1.6 文档基线（详见 [CHANGELOG](./status/CHANGELOG.md)）；2026-08-27 Phase 0 施工与验收（同日 CHANGELOG 条目）。
- 下一步：执行 [ROADMAP](./product/ROADMAP.md) Phase 1（任务 1.1 起，全部 schema + registry 扩充 + checker 脚本，1.16 收口接线）。两项待用户动作：① Phase 0 任务 0.6 的 AGENTS.md human sign-off（内容已提交，批准记录不得由 agent 伪造）；② 任务 0.9 分支保护随首个 `test/<iteration-id>` PR 出现 `release` 分支后在 7.5 收口。
- 需注意：历史审查记录已消化并按所有者指示删除；被否决的评审建议留痕于 [RISKS_AND_KNOWN_ISSUES](./status/RISKS_AND_KNOWN_ISSUES.md)，不得作为新需求重新引入。

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
| 环境 ENVIRONMENT_SETUP | [engineering/ENVIRONMENT_SETUP.md](./engineering/ENVIRONMENT_SETUP.md) | 已建立（命令均为"待实现"，未运行过） |
| 变更 CHANGELOG | [status/CHANGELOG.md](./status/CHANGELOG.md) | 已建立 |
| 风险 RISKS_AND_KNOWN_ISSUES | [status/RISKS_AND_KNOWN_ISSUES.md](./status/RISKS_AND_KNOWN_ISSUES.md) | 已建立 |

配套阅读顺序建议：PRD → GLOSSARY → ARCHITECTURE → DATA_MODEL → ROADMAP；工程实现前必读 engineering 三篇与相关 ADR。
