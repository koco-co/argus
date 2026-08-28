# 插件接口契约（ROADMAP 2.1）

状态：草案，等待用户明确签收（human sign-off）。本文件说明插件如何处理来源引用、职责边界及输出信封；不表示 `run_plugin.py` 已实现，也不替代人工确认。

信封结构的唯一机器权威是 [DATA_MODEL §10](../../docs/spec/architecture/DATA_MODEL.md#10-plugin-source-payloads)，Schema 位于 `plugins/_interface/schemas/`；落盘边界按 [ADR-006](../../docs/spec/architecture/adr/adr-006-source-payload-boundary.md) 执行。

## 1. fetch() → 先落盘，再校验

插件接收一个来源引用，返回来源载荷信封：

```text
fetch(source_ref: str, *, credentials: Mapping[str, str]) -> envelope dict
```

- 插件只返回规范化的来源载荷信封，不生成 M1/M4 拥有的内部工作流产物。
- `scripts/run_plugin.py` 是唯一调用入口；Skill 不得直接导入插件。运行器先将信封写入 `iterations/<id>/00-raw/source-payload.yaml`，再使用已注册的来源载荷 Schema 校验磁盘文件。
- 无效信封保留在原路径供排查，运行失败并指出具体违规 JSON 路径。该路径是隔离位置：下游 Skill 只有在校验成功后才能消费文件。
- `00-raw/` 下其他无关原始输入不属于该信封 Schema 的校验对象。

## 2. 内部产物转换由 M1/M4 负责

需求来源的转换属于 M1，API 来源的转换属于 M4。插件在信封边界结束，不负责直接产出 `requirements.yaml` 等内部产物，也不得为通过内部 Schema 而伪造工作流字段。

## 3. 安全与错误规则

以下规则来自 DATA_MODEL §10，即使 v1 没有真实插件也保持约束：

- **凭据**：仅来自环境变量或配置；不得硬编码、写入返回信封或输出到日志。
- **超时和大小限制**：每次 fetch 声明默认连接超时 5 秒、读取超时 30 秒，并由运行器执行响应大小与解压限制。
- **禁止访问私有网络**：抓取 URL 的来源必须拒绝私有地址、回环地址及链路本地地址，以限制 SSRF 风险。
- **不可信内容**：载荷中的指令式文本最多作为 M1/M4 的澄清材料，不是 agent 应执行的指令；未经独立佐证，不得写入 `knowledge/`。
- **结构化错误**：抓取失败时持久化 `error: {code, message}` 变体，不让原始异常跨越边界。Schema 强制成功与错误变体互斥：出现 `error` 时不得同时携带 `content`。

## 4. 注册与 v1 范围

`plugins/registry.yaml` 是唯一的插件名称到实现的映射表；`run_plugin.py` 只能通过该表解析插件，未知名称必须返回可操作的错误信息，不猜测替代插件。

按 PRD §8，v1 不交付真实连接器；按 DATA_MODEL §10 与 RISKS #17，v1 信封 Schema 只允许增加可选字段，破坏性变更留待首次真实集成处理。
