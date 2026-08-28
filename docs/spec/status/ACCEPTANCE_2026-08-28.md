# Argus v1 验收证据矩阵（2026-08-28）

本文件只登记实际执行结果；测试 fixture 的机器证据不冒充正式 iteration 的用户批准、外部通知或合并事实。

## 已验证事实

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 框架单元/集成测试 | 369 项通过 | `uv run pytest scripts/tests -q` |
| 静态与类型 | ruff、ruff format、pyright、6 个 pre-commit 钩子通过 | `make lint`；`uv run pre-commit run --all-files` |
| Medusa 靶场 | 全新 build/up、连续健康检查、幂等 reset、seed canary、down/re-up 通过 | `knowledge/target-app-notes/medusa.md` |
| UI 生成链 | 需求→测试点→功能用例→POM→两条 Chromium 用例→traceability 完整 | `iterations/test-fixture-ui-e2e/`；`automation/web/` |
| API 生成链 | 需求→规范化 API→API 用例→Pydantic 模型/客户端→两条真实 API 用例→traceability 完整 | `iterations/test-fixture-api-e2e/`；`automation/api/` |
| 全栈并发回归 | 双 worker 下 UI 正向/负向与 API 正向/负向共 4 条通过 | 本地最终运行：`4 passed`；GitHub e2e 使用相同 Compose-only 生命周期 |
| 覆盖门禁 | UI `c-auto`、API `a-auto`、API endpoint coverage、反向 orphan closure 全部通过 | `check_coverage.py`、`check_api_coverage.py`、`check_orphan_tests.py` |
| 导出 | XMind 与 XLSX 各连续两次字节一致；XLSX 跨秒 core modified 固定 | UI SHA `2c5806…d2a42`；API SHA `ed1123…36da0` |
| M9 可修复 | locator 真实失败后只修改 POM，复跑通过 | `run-20260828T164100Z-ui01`、`run-20260828T174000Z-mobi` |
| M9 预算耗尽 | 不可用生成桩连续 5 轮真实失败后 `budget_exceeded` | `run-20260828T171000Z-stub` |
| M9 产品差异 | 错误总额预期被分类为 `product_behavior_mismatch`，立即升级，预算保持 5/5 | `run-20260828T172000Z-prod` |
| M9 防伪 | 常量返回 patch 虽在路径白名单内，仍被 POM `stub-return` 启发式拒绝并回滚 | `run-20260828T173000Z-lite` |
| 视觉 | 真实折扣购物车在 `1440×900` 与 `390×844` 的顶部、总额、底部滚动状态已截图检查 | `run-20260828T164100Z-ui01/visual-verdict.md` 与该 run 的 `traces/` |
| 分支保护 | `release` 严格要求 `static-checks`、`e2e`、1 名非作者批准、last-push approval；禁止强推/删除 | `docs/spec/status/BRANCH_PROTECTION_2026-08-28.md` |
| GitHub Actions | SHA 固定的 static-checks 已在 `ac1cf71` 通过；完整 e2e 在前一提交真实通过，当前提交运行中 | Actions run `33158724904`、`33158309244`、`33158724876` |

## 不可伪造的外部事实

下列条目只能由其真实责任方或真实外部系统产生，agent 不得为追求“全绿”手写或降级：

1. 正式 UI/API iteration 的 M1/M2/M8 approval 必须由用户针对具体工件明确接受，再由 `record_approval.py` 写入。
2. `config/notify.yaml` 与真实 IM/邮件端点尚未提供；适配器、隔离重试和 CI `always()` 已验证，但“真实频道收到消息”未成立。
3. PR #1 仍为 Draft，且受保护 `release` 要求至少一名非作者人工批准；作者不能批准自己的 PR。
4. `finalize_merge.py` 需要真实 PR 合并 SHA；合并前不得伪造 `state: merged` 或 merge event。
5. Skill 自优化只有候选达到量化阈值并由用户确认具体 proposal diff 后才能应用；当前候选注册表为空。

这些事实未成立前，Roadmap 对应人工门禁保持未勾选，且不得宣称 v1 最终验收完成。
