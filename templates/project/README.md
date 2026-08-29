# Argus project template

这是 Argus 0.2.0 项目适配器的 clean-break 模板说明。项目模板只提供目标项目边界和配置约定，不复制或执行 Agent Runtime。

新项目应通过目标项目适配器声明 `web`/`api` workstream，通过 `argus-core` 持久化 iteration，通过 `argus-plugin-sdk` 注册来源连接器；项目级 Skills 仍保留在 `.agents/skills/`。真实凭据只能由运行环境注入，不能写入模板或 source envelope。
