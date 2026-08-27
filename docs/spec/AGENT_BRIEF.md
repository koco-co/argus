# 项目接续入口 / Agent Brief

核对日期：2026-08-27

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）处于**设计基线完成、实现未开始**阶段：全套规范文档按 product / architecture / engineering / status 四域组织于 `docs/spec/`，已完成 v1.5 契约闭环（吸收 Claude、Grok、外部 GPT 与 v1.4 复审建议 + 原有审查共识 + 行业实践校准）。本仓库目前仅含文档，无产品代码。

## 已完成与下一步

- 已完成：v1.0–v1.4 文档修订为 v1.5（消化针对 v1.4 的复审 20 项：补需求 priority 字段、API-led 豁免生产阶段 `requirements_mapped`、events/state 唯一写入者 `record_event.py`、证据存储分层策略 [ADR-012](./architecture/adr/adr-012-evidence-storage-policy.md)、孤儿测试反向校验、种子注册表、CI flake/定期回归/record-ci 契约、finalize_merge 落任务等）。此前轮次：v1.4 消化外部 GPT 审查 48 项；更早融合去向见 [CHANGELOG](./status/CHANGELOG.md)。
- 下一步：执行 [ROADMAP](./product/ROADMAP.md) Phase 0 任务 0.1。唯一待用户确认的范围决策：在本仓库直接施工，还是按 `<target-app>-automation` 新建仓库后搬入本 spec 目录（后者符合设计意图）。
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
