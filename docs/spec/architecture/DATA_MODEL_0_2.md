# Argus 0.2.0 数据模型

`argus-core` 的 Pydantic 模型是运行时契约；静态 iteration Schema 位于 `packages/argus-core/src/argus_core/schemas/iteration.schema.json`。未知字段拒绝，时间字段必须带时区，Schema 版本固定为 `2.0`。

## 1. IterationDocument

`IterationDocument` 持久化以下字段：

| 字段 | 含义 |
| --- | --- |
| `iteration_id` | 小写、2–64 字符的安全 ID |
| `status` | `created`、`active`、`accepted`、`promoted`、`blocked` 的聚合状态 |
| `revision` | 每次成功 Store 事务单调递增 |
| `created_at`/`updated_at` | 带时区时间 |
| `workstreams` | 至少一个且 ID 唯一的 Web/API 工作流 |
| `approvals` | 只追加的审批事实，ID 唯一 |
| `events` | 只追加的生命周期事件，ID 唯一 |
| `delegation` | 可选的结构化用户授权 |
| `promotions` | 每个 workstream 最多一个 `MergeFact` |
| `metadata` | 适配器非秘密元数据 |

## 2. Workstream

`Workstream` 的 `surface` 是 `web` 或 `api`，初始状态为 `created`。Web 路由依次经过 `requirements_accepted`、`design_pending`、`automation_pending`、`ready`、`executing`、`passed`；API 路由在 `design_pending` 位置使用 `mapping_pending`、`spec_pending`、`cases_pending`。执行状态可转为 `budget_exceeded`、`escalated` 或带原因的 `blocked`，`blocked` 只允许用户恢复到 `created`。promotion 不可通过普通 transition 伪造。

## 3. Approval

审批的关键字段是 `workstream_id`、`stage`、`action`、`actor`、artifact 路径、artifact SHA-256 和记录时间。固定矩阵：

- `requirements`：仅 `user/accepted` 或 `user/rejected`；永远不接受 delegated；
- `design`、`mapping`、`cases`、`environment`：用户决定或 scope 内 agent delegated；
- `execution`：用户接受/拒绝或 scope 内 delegated；
- `promotion`：仅 `user/approved` 或 `user/rejected`；
- `skill_change`：用户决定或 scope 内 agent delegated。

`latest_approval()` 按追加顺序返回某 workstream/stage 最后决定，门禁不回看旧决定；审批时间必须保持追加顺序，且每个阶段只能在对应生命周期窗口记录。delegated 决定必须匹配 iteration 的 `DelegationGrant`、scope、basis SHA、时间窗、`delegation_id` 和非空 note。execution 终态的 acceptance 也是 promotion 的前置门禁。

## 4. MergeFact

promotion 的唯一输入是外部已核验的事实：

```yaml
workstream_id: api-stream
provider: github
repository: owner/repository
pull_request: 123
base_ref: release
merged: true
merge_sha: <40 位小写 SHA-1>
merged_at: <带时区时间>
source_url: https://github.com/owner/repository/pull/123
verified_at: <带时区时间>
verifier: <独立 verifier 标识>
verification_signature: <绑定上述字段的签名摘要>
```

`verifier` 与 `verification_signature` 由外部 verifier 生成并随 promotion 持久化；没有可信 verifier key 或签名不匹配时，CLI/Store 拒绝 promotion 或读取被篡改的已 promotion 文档。当前实现使用由环境注入的 HMAC key 绑定 `github-api` verifier 身份；密钥持有与真实 GitHub 查询仍必须由受信任的外部 verifier 负责。`argus-core` 只验证形状、审批和 workstream 状态；GitHub API 的真实 `merged`、`base_ref`、SHA、时间和非作者 review 由 `finalize_merge.py`/外部系统提供。任何 fixture、聊天记录、本地日志或 agent note 都不能生成 MergeFact。多 workstream iteration 必须为每条 workstream 收到事实后才聚合为 `promoted`。

## 5. SourceEnvelope

SDK 静态契约在 `packages/argus-plugin-sdk/src/argus_plugin_sdk/schemas/source_envelope.schema.json`：公共字段为 `schema_version: "2.0"`、`source_type`、`fetched_at`、可选 `source_ref`，结果必须恰好包含 `content` 或 `error` 一个。错误只使用稳定 code/message，不传播异常原文、URL 或凭据。

`PluginContext.credentials` 不参与 repr/JSON 导出。source content 被视为不可信数据，注册表在返回前拒绝 credential-shaped 字段和上下文 secret。连接器不会读取或修改 iteration 文件。

## 6. 文件边界

根 v1 工件继续由原有 `scripts/schema_registry.yaml` 管理；0.2 工件只由 `argus-core`/`argus-plugin-sdk` 各自注册表管理。0.2 不解释 v1 `schema_version: "1.0"`，不修改 v1 artifact，不提供迁移脚本。
