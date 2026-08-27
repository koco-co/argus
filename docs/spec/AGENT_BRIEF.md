# 项目接续入口 / Agent Brief

核对日期：2026-08-28

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）处于 **Phase 0 已关闭、Phase 1 进行中**阶段。Phase 0（0.1–0.8）全部按 DoD 验证：uv + Python 3.12 工具链、pyproject/Makefile/.gitignore、pre-commit 守卫（远程 ruff 强制，四个本地校验钩子为指向 1.2/1.3/1.9/1.13 的显式桩）、ARCHITECTURE §2 目录骨架、`iteration.schema.json`（DATA_MODEL §3 逐字）+ schema registry + `scripts/new_iteration.py`（43 pytest 全绿，全新 clone 退出条件三连验收通过）。0.6 AGENTS.md 已获用户签收（2026-08-28）；0.9 分支保护推迟至 7.5。规范文档 v1.6 契约闭环维持不变。已确认决策：本仓库直接施工；通知 DoD 允许"dispatcher 单测 + 本地验证"降级留痕（webhook 后补）；每完成一个 Phase push 一次。

运行模型要求（非约束性建议）：驱动会话的模型应具备可靠的代码理解、AST 级结构与测试框架知识（参考 NIST Agent Evaluation 的任务能力框架）；Roadmap 5.5 的四个自调试证明用例可直接用作模型验收基准。

## 已完成与下一步

- 已完成：v1.0–v1.6 文档基线（详见 [CHANGELOG](./status/CHANGELOG.md)）；2026-08-27 Phase 0 施工与验收；2026-08-28 Phase 0 关闭（0.6 签收 + 决策留痕）。
- 进行中：Phase 1 已完成 1.1（全部 DATA_MODEL schema + fixture 对 + 文档块测试，含 rfc3339-validator 规格缺陷修复）、1.2（registry 十项绑定 + validate_schema.py 真实现 + _registry_lib 单一实现）、1.3（validate_iteration.py：分支感知路由/staleness 全链/审批与事件完整性/单迭代/run-summary 不变量，check 与 --fix 分离）、1.4（render_md.py 确定性渲染 requirement.md/test_points.md，金样 fixture 锁定）、1.5（export_xmind.py：XMind ZEN zip 布局、ZIP 时间戳与文档属性固定实现字节可复现、iteration→module→R→T→C→step 结构断言、argus_v<N>_Cases.xmind 版本号递增不覆盖）、1.6（export_xlsx.py：DATA_MODEL §7 十五列契约 openpyxl 回读断言、doc 属性与 ZIP 时间戳固定实现双跑同字节、argus_v<N>_API_Cases.xlsx 版本号递增）、1.7（check_coverage.py：每次运行先做引用完整性，五个分层 tier + from-iteration 状态驱动选择 + auto 本地聚合，exemptions 仅在 accepted 且带原因时生效，automation_test_ids 经进程内真实 pytest collection 交叉验证——嵌套收集以 cwd/sys.path/conftest 隔离防止状态泄漏）、1.8（check_api_coverage.py：每个非 out_of_scope endpoint 需 happy+negative/edge 且报错带 operation_id，out_of_scope 空原因必拒、完全省略 flag 合法，case 必须带 requirement_ids，未豁免 requirement 必须被引用——仅 not_testable 免 R→A，manual_only 不免；139 pytest 全绿）。- 下一步：Phase 1 任务 1.9（check_db_readonly.py）起，顺序至 1.15b，再 1.16 接线收口、1.17/1.18 补齐。待用户动作：无。
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
