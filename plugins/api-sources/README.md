# API 来源连接器占位

v1 不交付 OpenAPI、HAR、Postman 或 Swagger UI 的真实连接器。本目录保留接口位置，不表示已经完成平台接入。

后续实现必须遵循 [插件接口契约](../_interface/contract.md)，通过 `plugins/registry.yaml` 注册，并仅由 `scripts/run_plugin.py` 调用。连接器返回 API 来源信封，不直接生成 `api/spec.normalized.yaml`、用例或自动化代码；M4 负责规范化，M5 负责用例设计。

已有 API 信封可用 `uv run python scripts/run_plugin.py --payload <文件> --iteration iterations/<id>` 导入。抓取失败的 `error` 变体不得携带 `content`；Schema 合法的失败信封仍返回非零退出码，不能被当作成功输入。
