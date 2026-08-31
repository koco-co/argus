# ADR-013：0.2.0 clean-break monorepo

- 日期：2026-08-29
- 状态：Accepted

## Context

v1 是面向单一项目的仓库，控制面脚本、项目级 Skills、生成自动化和目标应用资产共存。将其直接发布为通用库会把历史目录、迁移语义和项目 secrets 带入公共 API，也会诱导实现 Agent Runtime。

## Decision

0.2.0 采用 clean-break workspace：

1. `packages/argus-core` 只拥有版本化控制面模型、状态、审批、Store、promotion 和中文 CLI；
2. `packages/argus-plugin-sdk` 只拥有来源插件契约、显式注册表和受限只读连接器；
3. `adapters/medusa` 只拥有目标项目的 workstream、URL 和非秘密适配声明；
4. 项目级 Skills 仍是 Markdown 资产，不进入任何 package，也不由 CLI 解释；
5. v1 的 `iterations/` 与 v1 schemas 不被 0.2 core 读取，不提供兼容层或迁移工具；
6. 所有 workspace 成员固定为 `0.2.0`，使用 Apache-2.0。

## Consequences

核心可以独立构建和复用，插件边界可以测试和替换，Medusa 适配器不会把项目事实混入通用控制面。代价是 v1 artifact 必须继续由旧脚本维护，升级者需要按新模型重新创建 iteration；这是有意的版本断裂，不应伪装成兼容。

## Rejected alternatives

- **把 Skill 文本放进 core**：会形成不可审计的执行器/Agent Runtime，违反边界。
- **让 CLI 自动扫描插件**：动态导入扩大供应链和凭据边界；改为宿主显式注册。
- **在 core 中同时保存 v1/v2 文档**：会产生隐式迁移和双重语义；保留单一 2.0 writable contract。
