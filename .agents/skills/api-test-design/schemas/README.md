# Schema 资源

本目录是 `api/spec.normalized.yaml` 与 `api/cases.yaml` 的唯一机器契约归属；`scripts/schemas/` 只拥有迭代生命周期、豁免、追溯和执行证据等共享 Schema。所有路径通过 `scripts/schema_registry.yaml` 绑定，避免版本漂移。

每个 API case 必须声明 `side_effect`，并在 `expected_response.body_assertions[]` 中使用带 JSONPath、操作符、值类型和 expected 的类型化业务断言。需要从 seed、当前/前置响应或请求派生的金额/数量必须写入 `derived_oracles[]`，声明输入来源、输入 JSONPath、表达式、结果类型和可选容差；自动化生成器不得自行添加 canonical case 未声明的业务断言。
