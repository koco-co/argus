# argus-plugin-sdk

Argus 0.2.0 的来源连接器契约：声明插件能力、隔离凭据、校验 source envelope，并提供受限的 GitHub Issues 与 OpenAPI 参考连接器。

静态 envelope Schema 和显式注册表位于 `src/argus_plugin_sdk/schemas/`。连接器只读外部来源，不能写 iteration、调用模型、组装 Prompt 或执行项目级 Skill；本包不是 Agent SDK。
