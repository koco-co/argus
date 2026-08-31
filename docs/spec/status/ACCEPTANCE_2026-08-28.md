# Argus v1 验收证据矩阵（2026-08-28，2026-08-31 更新）

本文件只登记实际执行结果；测试 fixture 的机器证据不冒充正式 iteration 的用户批准、外部通知或合并事实。

本轮用户已明确授予当前任务持续代理决策权。对仓库内正式 iteration 的需求、豁免、环境和终态验收，agent 在完成 Schema、覆盖、来源及真实行为审查后，使用 `scripts/record_approval.py` 记录 `action: delegated, actor: agent`；这不冒充用户亲自接受，也不扩展到外部通知、非作者审查或合并。

## 已验证事实

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 框架单元/集成测试 | 历史记录 430 项通过；2026-08-31 当前复核 529 项通过 | `uv run pytest scripts/tests -q` |
| 静态与类型 | ruff、ruff format、pyright、6 个 pre-commit 钩子通过 | `make lint`；`uv run pre-commit run --all-files` |
| Medusa 靶场 | 全新 build/up、连续健康检查、幂等 reset、seed canary、down/re-up 通过；SELECT-only 数据库角色可读且真实建表被拒绝 | `knowledge/target-app-notes/medusa.md` |
| UI 生成链 | 历史运行曾完成 10/10；2026-08-31 最新本地复核使用真实靶场完成 8/8 | `iterations/2026-08-medusa-ui-checkout/`；`automation/web/`；历史 run `run-20260828T183412Z-ui03`；最新补充 manifest `runs/run-20260831T072318Z-f0f7/`（code SHA `1b822c9`，JUnit `ca3fb2f…`，Allure `8e0b94e…`） |
| API 生成链 | 历史运行曾完成 22/22；2026-08-31 最新本地复核使用真实靶场完成 20/20 | `iterations/2026-08-medusa-api-checkout/`；历史 run `run-20260828T182611Z-api3`；最新补充 manifest `runs/run-20260831T070952Z-bc7c/`（code SHA `1b822c9`，JUnit `577225d…`，Allure `7b1193d…`） |
| 全栈完整回归 | 当前复核分面完成：Web 8/8、API 20/20；另有框架靶场健康与 seed canary 通过 | API/Web 分面命令及真实靶场证据；完整合并套件未在本轮重复执行 |
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
| GitHub Actions | 交付提交 `be7f421702fee51890ab2d1b9a0b9c9df5653262` 与 head `59618d5ca8296093fdde0c8745efa29133fecf6b` 的 `static-checks`、Compose-only `e2e` 均通过；修复前 main 手工 e2e 首轮 1 条 C0005 失败、自动唯一重试 38/38 通过，按工作流规则标记 `flaky-suspect`；PR #9 的 POM 时序修复 e2e 通过且分类 `normal`；合并后 main 手工 e2e 再次为 38/38、分类 `normal`；通知步骤从 Actions Secrets 环境变量装配并在无 Secret 时安全按零渠道执行 | 原 head Actions run `33203109968`、`33203109999`；修复前 main e2e run `33234802753`（job `99053798298`）；PR #9 e2e run `33236374652`；修复后 main e2e run `33236596449`（job `99058554054`）；历史对抗与回归 run `33167112164`、`33167112680`、`33167439010` |
| main 合并交付 | PR #1 已由 GitHub 真实合并到 `main`；PR #9 的 POM 时序修复也已由 GitHub 真实合并（代码 merge SHA `88f2b6abce9dfa5ded57db3191609f891fd3eed4`）；随后 PR #10、PR #11 文档更新继续真实合并（merge SHA 分别为 `aec57829a3fecd57b77d59c1ca73a175346c6215`、`dd5dacf62d92c528afedaab6f021cbbb9a535d45`）；`release` 未被上述操作改写 | `gh pr view 1`、`gh pr view 9`、`gh pr view 10`、`gh pr view 11`；`git ls-remote origin refs/heads/main refs/heads/release` |

## 当前复核收尾

2026-08-31 当前复核已用真实 Docker 靶场完成 fresh reset、seed、API checkout 20/20 和 Web checkout 8/8；执行后已 `target-app-down`，容器、网络和数据卷均已清理。最新本地补充 manifest 分别为 `runs/run-20260831T070952Z-bc7c/` 与 `runs/run-20260831T072318Z-f0f7/`，均绑定被测代码 SHA `1b822c92dc24487b03104171c0eeb7c2410a38e9`，并保留精确 collection/outcome、JUnit/Allure 和环境摘要；随后提交 `ca851aa` 的 GitHub static-checks run `33369318287` 与 e2e run `33369360450` 均成功，CI artifact `9749578091` 保留 API/UI manifest，trusted notification run `33369764953` 执行成功但为零渠道。后续仅补充文档与证据文件，不改变被测自动化代码。真实通知送达、非作者 PR 审批、受保护 merge 和 merge SHA 仍是外部事实。

## 不可伪造的外部事实

下列条目只能由其真实责任方或真实外部系统产生，agent 不得为追求“全绿”手写或降级：

1. 正式 UI/API iteration 的上游与终态记录已按当前任务授权完成：UI 记录用户 `accepted`，API 的 exemptions/environment/acceptance 记录 `delegated`；API 的结构化 delegation 绑定用户 basis 摘要、scope 和有效期，且旧终态已经 reopen 后由 fresh run 重建；所有批准记录由 `record_approval.py` 写入并绑定当前摘要。该代理授权不改变外部事实门禁。
2. `config/notify.yaml` 不存在，Actions Secrets/Variables 当前为空；适配器、隔离重试、Secrets 环境变量装配和 CI `always()` 已验证，但“真实频道收到消息”未成立。
3. PR #1 已于 2026-08-29 真实合并到 `main`，merge SHA 为 `f7fb82a5196aa665f47cdf22928b5bd7c2887f07`；随后 PR #9 的 Medusa 订单确认时序 POM 修复也已真实合并，代码 merge SHA 为 `88f2b6abce9dfa5ded57db3191609f891fd3eed4`；PR #10、PR #11 文档更新继续真实合并，merge SHA 分别为 `aec57829a3fecd57b77d59c1ca73a175346c6215`、`dd5dacf62d92c528afedaab6f021cbbb9a535d45`。受保护 `release` 仍停在 `c51649fe0e05db9c71077eec33773d114ceaf5d2`，其合并仍要求至少一名非作者人工批准与最后推送后的批准。
4. `finalize_merge.py` 的 v1 收口目标是受保护 `release`；必须使用该真实合并事实对应的 SHA，合并前不得伪造 `state: merged` 或 merge event。
5. Skill 自优化只有候选达到量化阈值并由用户确认具体 proposal diff 后才能应用；当前候选注册表为空。

## main 合并后复核

`main` 的手工回归 run `33234802753` 首轮在 `automation/web/tests/checkout/test_2026-08-medusa-ui-checkout_c0005_place_order.py::test_place_order[chromium]` 等待精确成功标题时超时；页面已进入真实订单确认路由并出现 `Order Confirmed`，但当时无目标 heading。工作流仅重试一次，第二轮 38/38 通过并按约定标记 `flaky-suspect`，因此该次 CI 不能被表述为无波动全绿。随后本地 fresh reset 后对 C0005 独立重放 3 次均通过，再执行完整 38 条套件为 38/38（125.82 秒）；未修改冻结断言或以较弱定位器掩盖该时序证据。

在上述复核后，PR #9 仅修改 `automation/web/pages/checkout/checkout_page.py` 的允许 POM 等待面：下单后先等待 `/order/<id>/confirmed` 路由，再等待既有精确成功标题；未修改冻结断言、需求或测试点。PR #9 的 e2e run `33236374652` 通过并分类 `normal`。其真实合并后的 `main` 手工 run `33236596449` 在 Compose-only 环境中为 `38 passed in 82.15s`，分类 `normal`，run evidence 已上传并完成靶应用清理。该次通知仍因没有 `config/notify.yaml` 或 Actions Secret/Variable 而为零渠道，不能作为真实外部送达证据。

## Phase 9 / PRD §7 逐项复核

| PRD §7 标准 | 当前证据 | 判定 |
| --- | --- | --- |
| 1. UI-led 与 API-led 两个独立 iteration 从原始需求到合并、可追踪自动化，且不手写 iteration 用例 | [UI iteration](../../../iterations/2026-08-medusa-ui-checkout/iteration.yaml) 与 [API iteration](../../../iterations/2026-08-medusa-api-checkout/iteration.yaml) 均为 accepted，分别有最新本地 UI 8/8、API 20/20 与 branch-specific traceability；[PR #1](https://github.com/koco-co/argus/pull/1) 与 [PR #9](https://github.com/koco-co/argus/pull/9) 已合并到 `main`；[PR #20](https://github.com/koco-co/argus/pull/20) 已创建并指向 `release` | **未满足 release 条件**：提交 `ca851aa` 的 GitHub static-checks/e2e 已成功，但 PR #20 仍缺非作者批准与受保护 `release` 合并，不能把 `main` 合并冒充 v1 退出 |
| 2. 所有确认门禁可从 iteration 目录重建 | 两个 `iteration.yaml` 的 `approvals[]`、`events[]`、`source_manifest[]` 与产物摘要完整；UI 用户 accepted、API requirements 用户 accepted 及后续 delegated 记录均由 `record_approval.py` 写入 | 通过（仓库内证据） |
| 3. 两条分支的完整 coverage chain 与豁免原因 | `check_coverage.py --tier from-iteration`、`check_api_coverage.py`、`check_orphan_tests.py` 均通过；API 的 R→A→nodeid 与 UI 的 R→T→C→nodeid 均有 traceability | 通过（当前 iteration 证据） |
| 4. attempts、diff、patch-scope、恢复检查点证明无中途用户接触且未修改冻结范围 | M9 四类证明 run、正式 UI/API run 的 `run-summary.yaml`、`check_patch_scope.py` 与恢复检查点测试均通过；PR #9 只改允许的 checkout POM 等待，不改断言/期望/测试点 | 通过（会话/仓库证据） |
| 5. GitHub Actions static-checks 与目标靶场 e2e | [本轮 static-checks](https://github.com/koco-co/argus/actions/runs/33369318287) 与 [本轮 e2e](https://github.com/koco-co/argus/actions/runs/33369360450) 均在提交 `ca851aa` 上成功；e2e 日志为 API 20/20 + UI 8/8、分类 `normal`，artifact `9749578091` 含 CI manifests；可信通知 run `33369764953` 执行成功但因无配置为零渠道 | 通过（当前提交的 GitHub 机器证据）；真实频道送达仍未验收 |

该逐项复核显示可在仓库内完成的证据已齐备；Roadmap 7.2、7.6、9.2、9.3 仍分别受真实通知渠道、非作者审批及受保护 `release` 合并/收口约束，8.2 目前没有达到阈值的候选，因此 9.5 总体保持未勾选。

这些事实未成立前，Roadmap 对应人工门禁保持未勾选，且不得宣称 v1 最终验收完成。
