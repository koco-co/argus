# ADR-014：execution manifest 使用 1.1 契约

- 状态：Accepted
- 日期：2026-08-30
- 范围：CI/E2E execution evidence

## Context

0.2.0 的 execution manifest 是新增加的 JSON 证据工件。初始实现把它标成 `1.0`，但同时引入了 collection nodeid、逐 attempt 的 collection、执行 outcome、JUnit/Allure digest、代码 SHA、环境和靶场摘要；这会把一次不兼容的契约变更伪装成旧版本。

## Decision

execution manifest 和 opt-in pytest execution evidence 使用 `schema_version: "1.1"`。`scripts/schema_registry.yaml` 的 `execution_manifest` binding 指向这份新契约，写入器只生成和接受 1.1。每个 attempt 独立保存 `expected_nodeids`、`collected_nodeids`、`executed_nodeids` 和完整 `outcomes`；跨 iteration 的 executed nodeid 被拒绝。traceability 可记录稳定的未参数化测试选择器；记录器只将其解析为 pytest 在同一选择器后追加的参数后缀（例如 `[chromium]`），并在 manifest 中保存实际收集/执行的 nodeid。

0.2 clean-break 不迁移 v1 `iterations/`，因此不存在需要自动转换的 accepted manifest。若未来需要读取历史 1.0 manifest，必须新增显式兼容 binding/reader 和迁移 ADR；不得放宽 1.1 Schema 或把缺失 collection 当作完整证据。

## Consequences

- CI 必须为每个 iteration 单独执行并调用 `record-ci-auto --iteration`；共用联合 JUnit/执行清单会被拒绝。
- 首轮和 retry 保留在同一个 iteration manifest 的独立 attempts 中，不覆盖首轮 digest。
- 旧的仅有 `nodeids`/无 outcome 的 execution JSON 不能作为 1.1 证据。
- Schema、fixture、writer 和 workflow 必须一起更新；导出及控制面不能消费不完整 manifest。
