# AGENTS.md — 操作规则（唯一权威）

项目状态与开发文档入口：@docs/spec/AGENT_BRIEF.md

本文件是驱动本仓库的 agent 的**唯一操作规则来源**（Roadmap 0.6）。冲突时以 PRD/DATA_MODEL/ARCHITECTURE 的机器契约为准；流程以本文件为准。

## 1. 流水线与确认点

每个迭代（iteration）沿 PRD §5 的全局状态机推进；**每个 ⏸ 确认点必须停止并等待用户明确肯定**，不得推断、不得代答：

| 模块 | 确认点 | 停下条件 |
| --- | --- | --- |
| M1 需求澄清 | ⏸ | 歧义澄清完成后，用户显式接受 `requirements.yaml` |
| M2 测试点（仅 UI 分支） | ⏸ | 用户审阅 `test_points.yaml` + `exemptions.yaml` 后接受 |
| M3 功能用例 | — | schema 门禁；导出的 `.xmind` 路径须呈现给用户，等待其决定是否进入 M6 |
| M4/M5 API 规范化与用例 | — | schema 门禁（前置：需求映射/豁免完成） |
| M8 环境配置 | ⏸ | `settings.py check` 绿 + 用户提供真实参数后批准 |
| M9 执行 | ⏸ 仅终态 | `passed` / `budget_exceeded` / `escalated` 时交还用户；**循环中途零接触** |
| M13 技能自优化 | ⏸ | 用户确认 diff 后才可应用 |

## 2. approvals[] 唯一写入者

- `approvals[]` **只能**由 `scripts/record_approval.py` 写入；agent 不得手写、伪造或"补记"任何 approval。
- 任何确认点的推进都以存在对应用户确认记录为前提；无记录 = 未确认。
- `state` 与 `events[]` 只能由 `scripts/record_event.py` 写入；手改即校验错误。

## 3. 分支路由（v1 强制）

| 分支声明 | 路由 |
| --- | --- |
| `ui=true, api=false` | `functional-test-design` 完成 M1→M2→M3，再交给 Web automation |
| `ui=false, api=true` | M1 accepted 后停止，不生成 `test_points.yaml`，交给 `api-test-design` 完成 M4→M5 |
| `ui=true, api=true` | v1 非法，必须由 Schema/semantic validation 拒绝 |

## 4. accepted 不可变与 reopen

- accepted 的上游 YAML **不可直接修改**；必须通过 `scripts/reopen_iteration.py` 重开：保留既有 ID，下游标记 `stale`，stale 输入不得被生成/执行消费。
- 豁免走 `exemptions.yaml`（`not_testable` / `manual_only`，必须带原因），不得回改 requirements。

## 5. 澄清协议（≤3 问/轮）

- 每轮最多 **3 个最高优先级问题**；低优先级歧义留待后续轮次。
- 能给选项就给有限选项，并**显式标注推荐项**；可组合的关注点不得强行二选一。
- 歧义只能由用户回答或显式陈述解决——**禁止用臆测填充**；无法澄清就停在 `clarifying`。

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
