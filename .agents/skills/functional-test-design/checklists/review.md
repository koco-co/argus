# M1–M3 交付前自审

- [ ] 当前分支只有一个合法 `ui=true, api=false` 路由；没有把 API 规范化或自动化生成混入本 Skill。
- [ ] `requirements.yaml` 的每个 requirement 有稳定 `R####`、非空描述、来源和可判定优先级；所有真实歧义已回答，未用猜测填空。
- [ ] M1 acceptance 只由用户记录；agent delegation 不替代 requirements acceptance。
- [ ] `test_points.yaml` 的每个有效点引用真实 requirement；未覆盖项有 `not_testable`/`manual_only` 豁免及具体理由。
- [ ] 每个 functional case 有唯一 `module:<name>` tag、真实 `test_point_ids[]`、前置条件、可观察步骤预期和 case-level `side_effect`。
- [ ] `side_effect` 覆盖 setup、提交和重放：有创建/更新/删除副作用的用例不会被当作无副作用安全重跑。
- [ ] 派生金额/数量使用 seed registry 与明确规则，不复制未经来源证明的固定结果。
- [ ] `traceability.yaml` 按每个 `(requirement_id, test_point_id, functional_case_id)` 组合幂等写入，automation nodeid 可真实 collection。
- [ ] 运行 `validate_schema.py`、`lint_test_design.py --stage <stage>`、`check_functional_expectations.py`、覆盖检查和 `export_xmind.py`；导出物由脚本生成且可重新解析。
- [ ] accepted 上游未被直接编辑；任何变更均通过 `reopen_iteration.py`，下游 stale 未被生成或执行消费。
- [ ] 交付说明区分已验证事实、假设、未运行项和需用户决定的产品冲突；不把 fixture、mock 或本地判断写成真实外部事实。
