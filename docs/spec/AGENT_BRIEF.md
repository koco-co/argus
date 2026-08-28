# 项目接续入口 / Agent Brief

核对日期：2026-08-28

## 最新执行覆盖：完整交付 Goal

用户最新指令要求持续实现全部剩余需求，只有成功使用框架完成真实开源靶项目的完整 Web/API 自动化代码验收，才能结束 Goal。已重新创建并读取确认原生 Goal 为 active；本页下方较早记录中的“等待 2.1 签收、不得进入 2.2”不再作为本次开发会话的暂停安排。此覆盖不等于伪造产品迭代的审批记录，也不删除框架应具备的确认、唯一写入者和验收审计能力。

当前新增实现：`scripts/run_plugin.py` 已具备注册表解析、子进程调用、信封导入、先落盘后 Schema 校验、结构化错误与安全失败行为；补齐两类来源的失败变体及互斥测试、两类来源目录说明和 AGENTS 链接。用户已于 2026-08-28 明确签收插件接口契约，Phase 2 的四项 DoD 已关闭。注册表仍无真实连接器（v1 明确不交付）。已有来源文件不被自动覆盖；来源不合法时保留隔离载荷并失败。未来连接器的逐跳重定向和实际连接安全仍需按接口契约实现，入口 URL 预检不等于网络沙箱。

本轮实际验证：`uv run --no-sync ruff check .` 通过；`uv run --no-sync pyright` 结果为 0 errors、0 warnings；`uv run --no-sync pytest scripts/tests -q` 为 **267 passed**；`run_plugin.py nonexistent ref` 返回 1 并提示注册表及信封导入用法；`git diff --check` 通过。尚未实现或验证真实靶应用与 Web/API 全流程，不将上述框架测试当作最终验收。当前实现未提交、未 push；进入本轮前的修改和两个临时文件删除均保留。下一步继续 Phase 3–6 的 Skills 与所需确定性脚本、靶应用和代码生成能力，之后完成 CI 与真实双分支验收。

## 当前状态

AI 驱动的自动化测试框架（"argus"；性能/load 测试保留至 post-v1）当前 **Phase 2 已完成，进入 Phase 3–6 的 Skill、靶应用与生成执行能力实施**。ROADMAP 已勾选 0.1–0.8、1.1–1.18 与 2.1–2.4；0.9 按既有安排延后至 7.5。Phase 1 的 schema、注册表、守卫脚本、唯一写入者、确定性导出、真实 pre-commit 钩子及 CI 接线已有实现（不再是桩）。本轮已重跑 ruff、pyright、267 项框架测试及全部 pre-commit 门禁并通过；前次自检也已通过 GitHub API 核实 Phase 1 提交 `1dd3d05` 的 [Actions static-checks 成功记录](https://github.com/koco-co/argus/actions/runs/33145443151)。

2026-08-28 前次真实自检：Docker daemon、Compose、uv、Python 3.12、项目 Playwright Chromium 实际启动、GitHub 远程读取与 Actions 配置读取均成功；账号具备仓库 ADMIN 权限。当时 `config/notify.yaml`、通知环境变量和仓库 Actions Secrets/Environments 均未配置，因此没有真实通知证据。历史自检记录可用 `git show 2b61331:docs/spec/status/STEP0_CHECK_2026-08-28.md` 复核；该临时文件的当前工作区删除状态予以保留。本轮未重复检查 webhook，也未将其标记为已验证。

规范文档仍以 v1.6 基线为权威。本轮用户明确禁止以 mock/本地单测替代真实依赖验收，覆盖历史“通知降级”许可；历史记录保留但不再作为当前验收依据。本仓库直接施工、每任务 conventional commit、每完成一个 Phase push 一次；人工确认点逐个等待明确确认，不从总目标推断授权。

最新用户执行要求：不影响当前任务/DoD 的问题先记台账，任务结束时统一汇总；只有当前依赖缺失、明确人工确认点或安全/授权边界才暂停，不反复检查未变化的非阻塞项。新增或修改的代码注释、文档备注使用中文。本轮通过 `get_goal` 核实原生 Goal 已包含修订规则且处于 active；其中复制进去的“正文尚未替换”前言是过时说明，不影响新版规则生效。临时提示词文件的工作区删除状态予以保留，不重建。

运行模型要求（非约束性建议）：驱动会话的模型应具备可靠的代码理解、AST 级结构与测试框架知识（参考 NIST Agent Evaluation 的任务能力框架）；Roadmap 5.5 的四个自调试证明用例可直接用作模型验收基准。

## 已完成与下一步

- 已完成：v1.0–v1.6 文档基线（详见 [CHANGELOG](./status/CHANGELOG.md)）；2026-08-27 Phase 0 施工与验收；2026-08-28 Phase 0 关闭（0.6 签收 + 决策留痕）。
- 已完成：Phase 1（1.1–1.18）全部任务按 DoD 完成。要点：全部 DATA_MODEL schema + fixture 对（1.1，含 rfc3339-validator 规格缺陷修复）；registry 十项绑定 + validate_schema/validate_iteration（1.2/1.3，状态机/审批/staleness/attempt 不变量）；render_md/export_xmind/export_xlsx 确定性渲染（1.4–1.6，字节可复现）；五层 coverage 门禁 + api 覆盖 + 六个防御性 checker（1.7–1.14）；patch-scope 与期望语义检查（1.15/1.15a）；三唯一写入者（1.15b）；pre-commit 四钩子真实施行 + ci.yml static-checks + 样本迭代 test-fixture-001（1.16，RED 冒烟验证）；prod-scope 审计与 orphan 反向闭包（1.17/1.18）；227 pytest 全绿。
- 需注意：历史审查记录已消化并按所有者指示删除；被否决的评审建议留痕于 [RISKS_AND_KNOWN_ISSUES](./status/RISKS_AND_KNOWN_ISSUES.md)，不得作为新需求重新引入。
- Phase 2 已完成：插件契约由用户明确签收；来源信封 Schema、运行器、失败变体、目录说明和 AGENTS 引用均已有代码、测试与提交证据。真实连接器仍按 PRD §8 保留到 post-v1。
- 当前下一步：按 Roadmap Phase 3–6 实现六个项目级 Skill、确定性辅助脚本、Medusa 靶场、Web/API 生成与自调试证据链。
- 非阻塞待办：真实通知 webhook。当前不影响 Phase 2–6；首次真实依赖在 Phase 7 通知 DoD（7.1/7.2），届时须用户提供 gitignored 配置/CI Secret 并实际验证；9.2/9.3 通知验收不豁免。后续动作与缺项在任务结束时统一汇总，不提前索取密钥，不重复探测未变化配置。
- 后续环境待办：`env.local.yaml`/`env.ci.yaml` 的真实参数和批准在相应 M8/CI 任务处理；不得伪造配置或批准，不以此提前阻塞无依赖的任务。
- 本次框架范围确认只关闭 Roadmap 2.1 的契约签收，不等于任何产品迭代的 requirements/test points/environment/acceptance 批准；这些记录仍须在对应产物生成后由唯一写入者脚本落账。

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
