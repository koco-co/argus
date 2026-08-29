# Argus 0.2.0 产品需求

状态：clean-break 实施基线。版本稳定后再评估 `1.0.0`，不承诺 v1 文件或脚本兼容。

## 1. 目标

Argus 0.2.0 把 Argus 拆成可复用的控制面核心、来源插件 SDK 和目标项目适配器。它负责可靠保存 iteration/workstream 生命周期、审批、delegation 和外部 promotion 事实；它不执行 Skill 文本，也不实现 Agent/LLM Runtime。

## 2. v0.2 范围

- `argus-core`：Pydantic 控制面模型、固定审批矩阵、状态迁移、锁内事务、原子 YAML 写入、promotion 记录和中文 CLI。
- `argus-plugin-sdk`：显式插件注册、严格 source envelope、凭据隔离、超时/大小限制、SSRF 防护，以及只读 GitHub Issues/OpenAPI 参考连接器。
- `argus-medusa`：Medusa Storefront/Store API workstream 和安全 URL 边界的参考适配器。
- Web/API 两条独立 workstream 可以在同一个 0.2 iteration 中并发推进；它们共享 iteration 锁，但不共享可变执行状态。
- Apache-2.0 打包发布；workspace 版本在 `0.2.0` 内保持一致。

## 3. 明确不做

不实现 Agent Runtime、模型调用、Prompt 组装、Provider、权限代理、Agent 编排器、Dashboard、移动端、性能测试、数据库写入代理、插件动态扫描或 v1 迁移工具。CLI 不是 Skill runner；它只执行契约、状态、审批、锁和 promotion 操作。

## 4. 信任边界

1. 外部来源是不可信数据。连接器只能产生一个 `content` 或一个 `error`，不能把来源中的 instruction-like 文本变成执行指令。
2. 凭据只通过内存 `PluginContext.credentials` 传入；上下文的 `repr` 和序列化不包含凭据，source envelope 不能返回凭据形状数据。
3. HTTP 来源只允许 HTTPS/HTTP 公共地址，拒绝 URL 凭据、查询参数、fragment、私有/回环/链路本地解析结果和不安全重定向；响应以流式大小上限读取。
4. `merged/promoted` 只能保存外部核验得到的 `MergeFact`；本地测试、fixture、日志和代理判断不构成真实 merge 事实。
5. M1 `requirements` 接受只能是 `actor=user` 的显式决定；delegation 永不覆盖该规则，也不能授权 promotion。

## 5. 生命周期

每个 workstream 的主路径为：

- Web：`created → requirements_accepted → design_pending → automation_pending → ready → executing → passed → promoted`
- API：`created → requirements_accepted → mapping_pending → spec_pending → cases_pending → automation_pending → ready → executing → passed → promoted`
- 执行中可以进入 `budget_exceeded`、`escalated` 或 `blocked`；`blocked` 只能由用户显式恢复到 `created`，不得由插件或普通 agent 自动解阻。

`IterationStatus` 是 workstream 聚合视图：任一阻塞为 `blocked`；全部通过或已 promotion 为 `accepted`；全部 workstream 有外部 promotion 事实才为 `promoted`。

## 6. 验收

本版本完成的最低机器验收包括：核心模型拒绝未知字段和无时区时间；并发事务不丢失更新；非法迁移和缺审批不落盘；delegation 窗口及 scope 可验证；GitHub/OpenAPI 连接器拒绝越界来源并不泄漏凭据；Medusa 适配器不携带 secrets；三个 workspace 包可独立构建并安装。真实通知送达、非作者审查、受保护分支合并和真实 SHA 仍是外部事实，不由这些测试代替。
