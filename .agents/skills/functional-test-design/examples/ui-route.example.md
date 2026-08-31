# UI 路由示例

目标：把一个真实需求送过 M1→M2→M3；不把 Schema 通过误当成用户接受，也不把派生视图当作源文件。

```bash
uv run python scripts/record_event.py iterations/demo-checkout \
  --from created --to requirements_clarifying --by agent
# 生成 requirements.yaml 后：
uv run python scripts/validate_schema.py iterations/demo-checkout/requirements.yaml
uv run python scripts/lint_test_design.py iterations/demo-checkout --stage requirements
# 只有用户明确接受 requirements 后，才调用 record_approval.py。
```

可模仿的 M3 case 形状（金额不写固定 oracle，副作用描述整个 case）：

```yaml
- case_id: C0001
  title: 使用真实种子商品完成结账
  priority: 1
  side_effect: creates
  precondition: 靶应用健康，购物车为空，已装载独立 seed namespace。
  test_point_ids: [T0001]
  tags: ["module:checkout"]
  steps:
    - action: 选择运行时解析的目标变体并加入购物车。
      expected: 购物车出现目标变体且数量为 1。
      expected_kind: ui_state
    - action: 提交订单并打开确认页。
      expected: 确认页展示订单号、商品和总额；购物车归零。
      expected_kind: derived_value
      derived_from:
        seed: discounted_total
        rule: product_price * (100 - discount_percentage) / 100
```

每次修改后重复运行 `lint_test_design --stage functional_cases`。发现事实不足就回到澄清；发现误报就修正规则，不能删断言、改成空 case 或绕过 lint。
