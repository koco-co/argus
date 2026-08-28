# 需求来源连接器占位

v1 不交付禅道、Jira、TAPD、蓝湖或 Figma 的真实连接器。本目录保留接口位置，不表示已经完成平台接入。

后续实现必须遵循 [插件接口契约](../_interface/contract.md)，在 `plugins/registry.yaml` 注册后由 `scripts/run_plugin.py` 调用。连接器只返回需求来源信封，不能读取迭代目录、生成测试用例或调用 LLM；转换为内部需求产物由 M1 完成。

已有 YAML 信封可用 `uv run python scripts/run_plugin.py --payload <文件> --iteration iterations/<id>` 导入。需要先通过 `new_iteration.py` 创建迭代。导入将先写入 `00-raw/source-payload.yaml`，再按统一注册表校验；无效信封保留且返回失败，不能交给下游消费。
