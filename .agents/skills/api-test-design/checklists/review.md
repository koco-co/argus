# M4–M5 交付前自审

- [ ] 当前 iteration 明确为 `ui=false, api=true`；requirements 已被用户接受，未生成 UI test points 或自动化代码。
- [ ] `exemptions.yaml` 只包含有依据的 `not_testable`/`manual_only`，每条理由非空；in-scope endpoint 都有真实 requirement mapping。
- [ ] normalized spec 保留 path/method、参数、request/response schema、components、`$ref`、组合器和 format；降级均有 `normalization_warnings[]`。
- [ ] 每个 in-scope operation 都有至少一个 happy 与一个 negative/edge case；每个 case 有稳定 `A####`、`requirement_ids[]`、module、`side_effect` 和可回放变量。
- [ ] `expected_response.body_assertions[]` 逐条声明 JSONPath、operator、`value_type` 和同类型 expected；`type` 断言的 expected 与 value_type 一致。
- [ ] 金额/数量等派生断言使用 `derived_oracles[]`；每个 oracle 有真实 seed/response/prev_response/request 输入、表达式、结果类型、目标路径和容差，并被对应的 `derived_equals` 引用。
- [ ] setup/replay 的副作用已按整个 case 声明；依赖 `prev_response` 的链没有误标 `side_effect: none`。
- [ ] `traceability.yaml` 按每个 `(requirement_id, api_case_id)` 组合幂等写入；M5 只写 R→A，不伪造 automation nodeid。
- [ ] 运行 Schema、`lint_test_design.py --stage api_spec/api_cases`、`check_api_coverage.py` 和 R→A 覆盖检查；XLSX 由 exporter 生成并 round-trip 校验 typed assertion/oracle 列。
- [ ] accepted requirements 未被直接编辑；任何上游变更均通过 `reopen_iteration.py`，stale 输入不会被规范化、生成、导出或自动化消费。
- [ ] 交付说明区分 source fact、推断、未探测响应和需用户裁决的问题；Schema/lint 通过不等同于真实 API 执行通过。
