---
name: self-debug-runner
description: 在 Argus 会话内执行 M9 测试、自调试、证据归档与会话恢复。用于已生成 Web/API 自动化且环境获批后的失败分类和受限修复；CI 只能只读执行测试，不得调用本 Skill 自动改代码。
metadata:
  version: "1.0.0"
---

# Outcome

在不接触冻结范围、不削弱断言且不中途联系用户的前提下，把可修复故障推进到通过，或形成完整的 budget/escalation 诊断证据。

## Routing

- 入口要求 automation generated、`settings.py check` 通过且 environment approval 已记录。
- CI 只使用 `self_debug_helper.py record-ci` 记录单次执行，不进入修复循环。
- escalation-only 证据立即终止；不得被模型降级为可修复分类。

## Steps

1. 读取 PRD §4.7、ADR-004、当前 run 目录与 `state.json`。若 `verification_pending=true`，恢复后的第一项动作必须是完整验证组合（verification battery）；完成前不得判断或应用新 patch，attempt 从 checkpoint 的编号继续。
2. 入口状态为 `env_configured` 时先用 `../../../scripts/record_event.py` 记录 `env_configured → executing`，再对 iteration 声明的完整目标 module set 做首次执行并由证据记录器落盘。首次全部通过则直接进入 `execution_passed`，不得虚构失败子集。
3. 通过 `../../../scripts/classify_failure.py` 机械分类。assertion/product mismatch、auth、5xx、environment、requirement conflict 与非 reseed fixture error 直接 escalated；普通失败才进入修复循环。
4. 每个 cycle（修复周期）严格包含：一次 failing-subset 执行、至多一个允许清单 patch、静态验证组合、AST import closure 的 affected-module regression（受影响模块回归）。默认 debug budget 为 5。
5. patch 前由 evidence recorder 写入基线 checkpoint；patch 完成后、任何 rerun 或新判断前，必须持久化 `attempt_number`、`patched_files[]`、`verification_pending=true`。随后捕获 diff、Playwright trace 与脱敏 console/network 摘要；完整验证通过后才把 `verification_pending` 清为 false。patch 只能修改 Web pages/components 的 locator/wait/type/import 或 API clients/models 的 serialization/type/import；data issue 只能改 reseed wiring/namespace。
6. 每次自动重跑前读取 case 的 side_effect；`side_effect=creates/deletes` 只有先完成可验证的 `fresh reset` 并恢复独立 seed namespace 才可重跑，否则立即拒绝。运行 `../../../scripts/check_patch_scope.py`、ruff、pyright、POM、markers、orphan、layering 与 affected-module regression；静态失败消耗 budget 并还原该 cycle patch。
7. 通过 `../../../scripts/self_debug_helper.py` 追加 attempt、diff ref、verdict 与终态。连续两次近似相同差异（near-identical diff）、触碰冻结范围或 assertion density 下降立即 escalated。
8. 用 `../../../scripts/record_event.py` 把 `executing` 推进为 `execution_passed`、`execution_budget_exceeded` 或 `escalated` 中唯一匹配证据的终态。达到终态后才联系用户，提供全部 attempts、patches、trace/verdict 与最终差异；Phase 7 notifier 可用后同时调用 `../../../scripts/notify.py`，通知失败不得篡改测试终态。随后按 M12 合同记录经证实且可复用的知识。

## Guardrails

- 永久冻结 tests assertions/expected values、case expectations、fixtures expected_*、seed formulas、markers、collection config、config、Skill、AGENTS 与 allow-list 外路径。
- 禁止 skip/xfail、`assert True`、吞异常、删除/放松断言、移出 collection、常量返回桩或伪造证据。
- 标记为 `side_effect=creates/deletes` 的用例不得自动重跑；只有先完成可验证的 `fresh reset` 并恢复独立 seed namespace 后才可进入下一次执行。
- run evidence append-only；后续 run 不得覆盖先前目录。日志、trace 与附件必须先脱敏。
- 循环中间零用户接触；终态也不得宣称未执行的验证通过。

## Delivery

终态报告 status、failure class、budget 使用、每次 patch ref、静态/回归结果、重放证据位置及需要用户决定的真实产品或需求问题。
