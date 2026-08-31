# ADR-015：测试设计契约在 0.6 clean-break 中收紧

- 状态：Accepted
- 日期：2026-08-30
- 范围：`functional-cases.yaml` 与 `api/cases.yaml`

## Context

测试设计产物此前使用 `schema_version: "1.0"`，但仅依赖 JSON Schema 的字段形状不足以表达安全重跑副作用和可执行响应预期。0.6 收紧了两个契约：功能用例必须声明整个 case 的 `side_effect`；API 用例必须声明带 JSONPath、操作符、值类型和 expected 的 `body_assertions`，派生值还必须绑定 `derived_oracles` 的真实输入来源。这些要求会拒绝缺少字段的旧形状。

仓库当前处于 v1/v2 clean-break，测试设计产物不是对外稳定 API；没有需要继续消费旧形状的外部 reader，也不提供迁移工具。

## Decision

本次收紧作为 v1 首次发布前的 **clean-break 修订** 留在测试设计 Schema 的 `schema_version: "1.0"` 契约内。`1.0` 在这里表示当前测试设计工件族，而不是对缺少新必填字段的历史文件提供兼容承诺：

- Schema、`lint_test_design.py`、导出器、状态迁移和审批写入器共同拒绝旧形状；
- 已接受 iteration 的上游设计工件只能通过 `reopen_iteration.py` 重新生成/确认，不能直接修改；
- 自动化只消费通过 Schema 与设计 lint 的 canonical 断言，不得自行补充业务预期；
- 若未来测试设计工件已经对外发布或需要读取旧形状，必须另行引入 `schema_version: "1.1"`、兼容 reader/迁移方案和独立 ADR，不得把本次 clean-break 解释成向后兼容。

execution manifest 是新增加的证据工件，继续使用 ADR-014 规定的 `schema_version: "1.1"`，两者版本策略不混用。

## Consequences

- 旧的缺少 `side_effect` 或 `body_assertions` 的测试设计文件会在 lint、导出、状态迁移或审批前被拒绝；
- 设计 lint 的诊断是验收合同的一部分，必须包含稳定 rule ID、产物、YAML location、actual/expected 和修复建议；
- 版本升级不应被用来绕过本轮 clean-break；需要真实业务事实时仍必须回到澄清/重开流程。
