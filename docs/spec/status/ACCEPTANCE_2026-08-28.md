# Argus v1 验收证据矩阵（2026-08-28，2026-08-29 更新）

本文件只登记实际执行结果；测试 fixture 的机器证据不冒充正式 iteration 的用户批准、外部通知或合并事实。

本轮用户已明确授予当前任务持续代理决策权。对仓库内正式 iteration 的需求、豁免、环境和终态验收，agent 在完成 Schema、覆盖、来源及真实行为审查后，使用 `scripts/record_approval.py` 记录 `action: delegated, actor: agent`；这不冒充用户亲自接受，也不扩展到外部通知、非作者审查或合并。

## 已验证事实

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 框架单元/集成测试 | 430 项通过 | `uv run pytest scripts/tests -q` |
| 静态与类型 | ruff、ruff format、pyright、6 个 pre-commit 钩子通过 | `make lint`；`uv run pre-commit run --all-files` |
| Medusa 靶场 | 全新 build/up、连续健康检查、幂等 reset、seed canary、down/re-up 通过；SELECT-only 数据库角色可读且真实建表被拒绝 | `knowledge/target-app-notes/medusa.md` |
| UI 生成链 | 正式 UI：需求→测试点→功能用例→POM→8 条 Chromium 用例→traceability 完整；fresh reset 后 M9 10/10 | `iterations/2026-08-medusa-ui-checkout/`；`automation/web/`；最新 `run-20260828T183412Z-ui03` |
| API 生成链 | 正式 API：需求→映射/豁免→真实 Medusa 来源规范化→20 个 API case→Pydantic 模型/FullStoreClient→traceability 完整；fresh reset 后 M9 连同 fixture 22/22，A0018 缺少 provider 返回结构化 400 | `iterations/2026-08-medusa-api-checkout/`；最新 `run-20260828T182611Z-api3` |
| 全栈完整回归 | fresh reset 后正式 UI/API、既有 fixture 与靶场探针共 38 条通过 | 本地最终运行：`make target-app-reset && TEST_ENV=local uv run pytest automation/web automation/api -q --junitxml=/tmp/argus-fullstack-final-20260829.xml` → `38 passed in 122.71s`；双 worker 隔离证据仍见 5.1 记录 |
| 覆盖门禁 | UI `c-auto`、API `a-auto`、API endpoint coverage、反向 orphan closure 全部通过 | `check_coverage.py`、`check_api_coverage.py`、`check_orphan_tests.py` |
| PR 覆盖范围 | iteration 工件变化只检查对应目录；自动化、共享代码或覆盖门禁变化检查全部；删除 iteration 明确失败；CI 取得完整 base 历史 | `check_coverage.py --changed-base <sha>`；`test_check_coverage.py` |
| CI 对抗控制 | `force_failure` 远端连续两轮均为 1 失败/9 通过并以失败终止；`force_flaky` 首轮 1 失败/9 通过、第二轮 10 通过，被归类为 `flaky-suspect` 并以成功终止；两条路径均上传证据、执行汇总通知并清理容器/网络/卷 | Actions run `33167112680`、`33167439010`；artifact `9684097115`、`9684232762` |
| 导出 | XMind 与 XLSX 各连续两次字节一致；XLSX 跨秒 core modified 固定 | UI 历史证据；正式 API v4 `iterations/2026-08-medusa-api-checkout/exports/argus_v4_API_Cases.xlsx`，SHA 见导出日志 |
| M9 可修复 | locator 真实失败后只修改 POM，复跑通过 | `run-20260828T164100Z-ui01`、`run-20260828T174000Z-mobi` |
| M9 预算耗尽 | 不可用生成桩连续 5 轮真实失败后 `budget_exceeded` | `run-20260828T171000Z-stub` |
| M9 产品差异 | 错误总额预期被分类为 `product_behavior_mismatch`，立即升级，预算保持 5/5 | `run-20260828T172000Z-prod` |
| M9 防伪 | 常量返回 patch 虽在路径白名单内，仍被 POM `stub-return` 启发式拒绝并回滚 | `run-20260828T173000Z-lite` |
| Skill 黄金基线 | 四个生成 Skill 各有 1 份版本化冻结输入；10 项代表性 YAML/Python 产物通过 Schema、结构语义或 AST 语义比较，输入/YAML/AST 漂移反向测试均会失败 | `make skill-golden`；`scripts/tests/test_check_skill_golden.py` |
| 视觉 | 真实折扣购物车在 `1440×900` 与 `390×844` 的顶部、总额、底部滚动状态已截图检查 | `run-20260828T164100Z-ui01/visual-verdict.md` 与该 run 的 `traces/` |
| 分支保护 | `release` 严格要求 `static-checks`、`e2e`、1 名非作者批准、last-push approval；禁止强推/删除 | `docs/spec/status/BRANCH_PROTECTION_2026-08-28.md` |
| GitHub Actions | 交付提交 `be7f421702fee51890ab2d1b9a0b9c9df5653262` 与最新 head `59618d5ca8296093fdde0c8745efa29133fecf6b` 的 `static-checks`、Compose-only `e2e` 均通过；最新 e2e 日志显示 38 passed，通知步骤从 Actions Secrets 环境变量装配并在无 Secret 时安全按零渠道执行 | 最新 head 的 Actions run `33203109968`、`33203109999`；合并到 main 后 static-checks run `33234492727`；历史对抗与回归 run `33167112164`、`33167112680`、`33167439010` |
| main 合并交付 | PR #1 已由 GitHub 真实合并到 `main`，产生 merge SHA `f7fb82a5196aa665f47cdf22928b5bd7c2887f07`；`release` 未被该操作改写 | `gh pr view 1`；`git ls-remote origin refs/heads/main refs/heads/release` |

## 不可伪造的外部事实

下列条目只能由其真实责任方或真实外部系统产生，agent 不得为追求“全绿”手写或降级：

1. 正式 UI/API iteration 的上游与终态记录已按当前任务授权完成：UI 记录用户 `accepted`，API 的 exemptions/environment/acceptance 记录 `delegated`；API 的结构化 delegation 绑定用户 basis 摘要、scope 和有效期，且旧终态已经 reopen 后由 fresh run 重建；所有批准记录由 `record_approval.py` 写入并绑定当前摘要。该代理授权不改变外部事实门禁。
2. `config/notify.yaml` 不存在，Actions Secrets/Variables 当前为空；适配器、隔离重试、Secrets 环境变量装配和 CI `always()` 已验证，但“真实频道收到消息”未成立。
3. PR #1 已于 2026-08-29 真实合并到 `main`，merge SHA 为 `f7fb82a5196aa665f47cdf22928b5bd7c2887f07`；受保护 `release` 仍停在 `c51649fe0e05db9c71077eec33773d114ceaf5d2`，其合并仍要求至少一名非作者人工批准与最后推送后的批准。
4. `finalize_merge.py` 的 v1 收口目标是受保护 `release`；必须使用该真实合并事实对应的 SHA，合并前不得伪造 `state: merged` 或 merge event。
5. Skill 自优化只有候选达到量化阈值并由用户确认具体 proposal diff 后才能应用；当前候选注册表为空。

这些事实未成立前，Roadmap 对应人工门禁保持未勾选，且不得宣称 v1 最终验收完成。
