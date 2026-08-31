# Schema 资源

本目录是 `requirements.yaml`、`test_points.yaml` 与 `functional-cases.yaml` 的唯一机器契约归属；`scripts/schemas/` 只拥有迭代生命周期、豁免、追溯和执行证据等共享 Schema。所有路径通过 `scripts/schema_registry.yaml` 绑定，避免版本漂移。

`functional-cases.yaml` 的每个 case 必须声明完整副作用 `side_effect`（`none`、`creates`、`updates` 或 `deletes`）。该字段描述 setup、交互和提交的整体效果，供真实执行和安全重跑判断；它不是通过增加空断言来填补覆盖的替代品。
