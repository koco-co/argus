# AGENTS.md — 操作规则（唯一权威）

项目状态与开发文档入口：@docs/spec/AGENT_BRIEF.md

本文件是驱动本仓库的 agent 的**唯一操作规则来源**（Roadmap 0.6）。冲突时以 PRD/DATA_MODEL/ARCHITECTURE 的机器契约为准；流程以本文件为准。

## 1. 流水线与确认点

每个迭代（iteration）沿 PRD §5 的全局状态机推进。用户仍是确认的授权主体；若用户明确授予当前任务的持续代理决策权，必须先用 `scripts/record_delegation.py` 写入带 basis 摘要、scope、有效期的结构化 delegation，之后 agent 才能在授权范围内逐件审查并由唯一写入器记录 `action: delegated`。delegated 始终如实标记 `actor: agent`，不得写成用户亲自接受：

| 模块 | 确认点 | 停下条件 |
| --- | --- | --- |
| M1 需求澄清 | ⏸ | 歧义澄清完成后，用户显式接受 `requirements.yaml`；代理授权不得替代产品需求确认 |
| M2 测试点（仅 UI 分支） | ⏸ | `test_points.yaml` + `exemptions.yaml` 通过 Schema、覆盖和用户审查，或在结构化 delegation 的对应 scope 内记录 delegated |
| M3 功能用例 | — | schema 门禁；导出的 `.xmind` 路径留存后，在持续授权下可直接进入 M6 |
| M4/M5 API 规范化与用例 | — | schema 门禁（前置：需求映射/豁免完成） |
| M8 环境配置 | ⏸ | `settings.py check` 绿 + 用户提供真实参数后批准；结构化 delegation 可在 scope 内记录本地环境审查，但不创造参数授权 |
| M9 执行 | ⏸ 仅终态 | `passed` / `budget_exceeded` / `escalated` 时记录终态；循环中途零接触，终态须有用户接受或结构化 delegation 内的 agent 审查 |
| M13 技能自优化 | ⏸ | 仅在阈值和 golden 回归满足后，显式确认或结构化 delegation 内记录 delegated |

## 2. approvals[] 唯一写入者

- `approvals[]` **只能**由 `scripts/record_approval.py` 写入；agent 不得手写、伪造或"补记"任何 approval。`scripts/record_delegation.py` 只负责持久化结构化授权及一次性绑定旧版 delegated 记录，绑定后仍由 Schema/语义门禁复核。
- 显式用户决定使用原有 action 并记录 `actor: user`；结构化授权范围内的 agent 决定使用 `action: delegated` 并记录 `actor: agent`、`delegation_id` 和非空 note。writer 校验 delegation 的 basis_sha256、scope、有效期和批准时间，note 不能单独产生授权。
- 任何确认点的推进都以存在对应的 `accepted/provided/approved` 或 `delegated` 记录为前提；无记录 = 未确认。delegated 只适用于仓库内产物和本地执行流程，不能代替真实通知送达、非作者 PR 审批、受保护分支合并或合并 SHA。
- `state` 与 `events[]` 只能由 `scripts/record_event.py` 写入；手改即校验错误。agent 重开必须传入结构化 delegation 的 `lifecycle_reopen` scope；不能把普通 agent 事件冒充用户重开。

## 3. 分支路由（v1 强制）

| 分支声明 | 路由 |
| --- | --- |
| `ui=true, api=false` | `functional-test-design` 完成 M1→M2→M3，再交给 Web automation |
| `ui=false, api=true` | M1 accepted 后停止，不生成 `test_points.yaml`，交给 `api-test-design` 完成 M4→M5 |
| `ui=true, api=true` | v1 非法，必须由 Schema/semantic validation 拒绝 |

## 4. accepted 不可变与 reopen

- accepted 的上游 YAML **不可直接修改**；必须通过 `scripts/reopen_iteration.py` 重开：用户直接重开，或 agent 以结构化 delegation 的 `lifecycle_reopen` scope 重开；保留既有 ID，下游标记 `stale`，stale 输入不得被生成/执行消费。
- 豁免走 `exemptions.yaml`（`not_testable` / `manual_only`，必须带原因），不得回改 requirements。

## 5. 澄清协议（≤3 问/轮）

- 每轮最多 **3 个最高优先级问题**；低优先级歧义留待后续轮次。若用户已授予持续代理决策权，agent 应先依据原始需求、已接受上游产物和真实靶应用行为自行闭合可验证歧义，并在产物或 note 中记录假设；只有存在无法由这些事实决定的产品冲突时才保留 clarifying。
- 能给选项就给有限选项，并**显式标注推荐项**；可组合的关注点不得强行二选一。
- 歧义只能由用户回答、显式授权下的可追溯事实审查或真实来源证据解决——**禁止用臆测填充**；无法由事实决定时保留 `clarifying` 并记录阻塞原因。

## 6. 生产环境保护

- `TEST_ENV=prod` 时只运行带 `@pytest.mark.read_only` 的用例（collection 门禁机械生效）。
- `read_only` 标记是元数据，不是能力控制：真正的边界是 SELECT-only DB 角色与主机侧控制（PRD §6 分层）。

## 7. 其他强制规则（v1.3 起）

- v1 CI 以 GitHub Actions 为唯一权威；自愈（self-debug）只在会话侧运行，CI 只读执行已提交测试（ADR-004）。
- 派生视图（`.md`/`.xmind`/`.xlsx`）一律脚本再生，禁止手改；`exports/` 同理。
- automation 代码禁止在运行时读 `iterations/**`；测试只读自己的 pytest 标记。
- v1 每仓库最多一个非终态迭代（`scripts/new_iteration.py` 强制）。

## 8. 工具链速查

| 目的 | 命令 |
| --- | --- |
| 初始化（依赖 + chromium + hooks） | `make setup` |
| 新建迭代 | `make new-iteration ID=<id> BRANCH=ui\|api` |
| Lint | `make lint` |
| 框架自测 | `uv run pytest scripts/tests` |
| Schema 校验 | `make validate-iteration ID=<id>` |
| 导出 | `make export ID=<id>` |
| 生成的回归（UI/API） | `make web-tests\|api-tests MODULE=<m> ENV=<e>` |
| 靶应用 | `make target-app-up\|seed\|reset\|healthcheck\|down` |

详细说明：[ENVIRONMENT_SETUP](docs/spec/engineering/ENVIRONMENT_SETUP.md)（状态列标注"已运行"的命令才被验证过）。

插件层入口：[需求来源占位说明](plugins/requirement-sources/README.md)、[API 来源占位说明](plugins/api-sources/README.md)；v1 仅提供信封边界和运行器，不交付真实连接器。
