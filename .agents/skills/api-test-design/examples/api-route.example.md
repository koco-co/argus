# API 路由示例

M4/M5 只消费 accepted requirements 和真实来源。先规范化 endpoint，再生成 A####；不能从模糊文档猜 response Schema。

```bash
uv run python scripts/lint_test_design.py iterations/demo-api --stage exemptions
uv run python scripts/lint_test_design.py iterations/demo-api --stage api_spec
uv run python scripts/lint_test_design.py iterations/demo-api --stage api_cases
uv run python scripts/export_xlsx.py iterations/demo-api
```

每个 case 至少声明副作用和类型化业务断言；金额、数量等派生值写成可审计 oracle：

```yaml
- api_case_id: A0007
  requirement_ids: [R0002]
  operation_id: applyStoreCartPromotions
  endpoint: /store/carts/{id}/promotions
  method: POST
  case_type: happy_path
  side_effect: updates
  module: checkout
  request: {path_params: {id: "${cart_id}"}}
  expected_response:
    status_code: 200
    body_schema: {$ref: "#/components/schemas/CartResponse"}
    body_assertions:
      - path: "$.cart.total"
        operator: type
        value_type: number
        expected: number
    derived_oracles:
      - name: total
        target_path: "$.cart.total"
        expression: product_price * (100 - discount_percentage) / 100
        inputs:
          - {name: product_price, source: seed, path: "$.product_price_eur.value"}
          - {name: discount_percentage, source: seed, path: "$.discount_argus10.percentage"}
        value_type: number
        tolerance: 0.01
```

自动化生成器只能实现 canonical case 已声明的断言；若发现业务断言缺失，应回到 M5 修复 `api/cases.yaml`，而不是在测试代码中偷偷新增 oracle。
