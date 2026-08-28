---
name: web-automation-generation
description: 从 exported functional cases 为 Argus 生成 Playwright Python POM、fixtures、tests 与 traceability。用于 M6 和 Web iteration 的增量再生成；不得设计需求、生成 API 自动化或执行自调试修复。
metadata:
  version: "1.0.0"
---

# Outcome

把 Schema 合法的功能用例转换为可收集、POM 合规、基于真实种子 oracle 且可追踪的 Web 自动化代码。

## Routing

- 只处理 UI 分支且 `functional-cases.yaml.status=exported` 的 iteration。
- 输入未导出、stale、缺少 seed registry 或靶应用知识时停止，不生成占位测试。
- 运行后失败修复转交 `self-debug-runner`，不得在本 Skill 内弱化测试。

## Inputs / Outputs

- 输入：`functional-cases.yaml`、accepted requirements/test points、`shared/testdata/seed-registry.yaml` 与 `knowledge/target-app-notes/<target-app>.md`。
- 输出：`automation/web/{pages,components,fixtures,tests}/<module>/` 与当前 iteration 的 `traceability.yaml`。
- 既有长效资产按业务 module 复用；文件名为 `test_<iteration_id>_<case_id>_<behavior>.py`。

## Steps

1. 读取 PRD §4.5、CODING_STANDARDS 的生成规则、靶应用 notes 和 seed registry，运行 iteration、Schema、functional expectation 与 T→C 检查。
2. 在任何状态转换前比较全部输入 hash。若当前已是 `web_automation_generated`、hash 相同且 nodeid 仍可收集，则 no-op；不得产生格式噪声。只有确需首次生成且当前为 `functional_cases_exported` 时，才记录 `functional_cases_exported → web_automation_generating`；再生成必须先走 reopen/stale 协议回到合法状态。
3. 先搜索并复用 page/component 方法。新 locator 按 role→label→placeholder→text→testid→CSS 选择；使用后位策略时在代码中写明真实理由。
4. page/component 只封装 locator、action 与读取值；tests 只通过对象交互并持有 assertions。value 方法必须从 locator 派生，不得返回常量桩。
5. 从 seed context 运行时推导 expected value，不复制 derived literal。每个 test 添加 module、case_id、iteration markers，behavior 使用不含 ID、长度不超过 50 的 snake_case 动词短语。
6. 幂等 upsert traceability 的 C→nodeid；不得删除仍被其他 active iteration 引用的方法或 nodeid，retirement 必须有记录并通过 coverage。
7. 依次运行 ruff、pyright、`check_pom_boundary.py`、`check_test_markers.py`、`check_layering.py`、`check_functional_expectations.py`、`check_orphan_tests.py` 与 C→automation coverage。失败修复并重验最多 3 次；耗尽后通过 `uv run python scripts/record_event.py ... --to blocked --reason validation_budget_exhausted` 进入阻塞终态。
8. 收集实际 pytest nodeid 并再次验证 traceability；通过 `uv run python scripts/record_event.py ...` 记录 `web_automation_generating → web_automation_generated`。

## Guardrails

- tests 中禁止 selector literal，pages/components 中禁止 assert/expect。
- 禁止 hard wait、request interception 假绿、skip/xfail、`assert True`、吞异常或常量返回桩。
- automation 运行时不得读取 `iterations/**`，不得硬编码秘密或环境地址。
- 不直接修改 approvals/state/events，不覆盖无关用户资产。

## Delivery

报告新增/复用资产、生成 nodeid、traceability 变化、所有静态门禁结果与未执行的真实浏览器场景。
