# 项目接续入口 / Agent Brief

核对日期：2026-08-27

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）处于**设计基线完成、实现未开始**阶段：全套规范文档按 product / architecture / engineering / status 四域组织于 `docs/spec/`，已完成 v1.3 契约闭环（吸收 Claude 与 Grok 审查建议 + 原有审查共识 + 行业实践校准）。本仓库目前仅含文档，无产品代码。

## 已完成与下一步

- 已完成：v1.0/v1.1/v1.2 文档修订为 v1.3；补充 DATA_MODEL（含 exemptions 的机器 Schema）与 branch-aware 覆盖、API 追溯、期望值来源、导出结构、approval/reopen、CI 触发和自愈边界契约；新增 ADR-009，并同步 GLOSSARY、CODING_STANDARDS、TESTING_STRATEGY、ROADMAP、CHANGELOG。原 `Implementation Guide.md` 与 `Repo structure.md` 已分别融入 engineering 与 architecture 各文档后删除，融合去向见 [CHANGELOG](./status/CHANGELOG.md)。
- 下一步：执行 [ROADMAP](./product/ROADMAP.md) Phase 0 任务 0.1。唯一待用户确认的范围决策：在本仓库直接施工，还是按 `<target-app>-automation` 新建仓库后搬入本 spec 目录（后者符合设计意图）。
- 需注意：历史审查记录已消化并按所有者指示删除；被否决的评审建议留痕于 [RISKS_AND_KNOWN_ISSUES](./status/RISKS_AND_KNOWN_ISSUES.md)，不得作为新需求重新引入。

## 文档索引

| 职责 | 实际位置 | 状态 |
| --- | --- | --- |
| 接续 AGENT_BRIEF | 本页 | 已建立 |
| 需求 PRD | [product/PRD.md](./product/PRD.md) | 已建立 (v1.3) |
| 路线 ROADMAP | [product/ROADMAP.md](./product/ROADMAP.md) | 已建立 (v1.3) |
| 术语 GLOSSARY | [product/GLOSSARY.md](./product/GLOSSARY.md) | 已建立 |
| 架构 ARCHITECTURE | [architecture/ARCHITECTURE.md](./architecture/ARCHITECTURE.md) | 已建立 (v1.3) |
| 数据 DATA_MODEL | [architecture/DATA_MODEL.md](./architecture/DATA_MODEL.md) | 已建立（Schema 唯一权威） |
| 决策 ADR | [architecture/adr/](./architecture/adr/) （adr-001…009） | 已建立 |
| 编码 CODING_STANDARDS | [engineering/CODING_STANDARDS.md](./engineering/CODING_STANDARDS.md) | 已建立 |
| 测试 TESTING_STRATEGY | [engineering/TESTING_STRATEGY.md](./engineering/TESTING_STRATEGY.md) | 已建立（含靶应用 harness/种子策略） |
| 环境 ENVIRONMENT_SETUP | [engineering/ENVIRONMENT_SETUP.md](./engineering/ENVIRONMENT_SETUP.md) | 已建立（命令均为"待实现"，未运行过） |
| 变更 CHANGELOG | [status/CHANGELOG.md](./status/CHANGELOG.md) | 已建立 |
| 风险 RISKS_AND_KNOWN_ISSUES | [status/RISKS_AND_KNOWN_ISSUES.md](./status/RISKS_AND_KNOWN_ISSUES.md) | 已建立 |

配套阅读顺序建议：PRD → GLOSSARY → ARCHITECTURE → DATA_MODEL → ROADMAP；工程实现前必读 engineering 三篇与相关 ADR。
