# Argus 0.2.0 架构

状态：clean-break monorepo 架构基线。v1 的 `iterations/`、项目级 Skills 和生成自动化是历史项目资产；0.2 控制面不读取它们，也不提供迁移层。

## 1. Workspace

```text
argus/
├── packages/
│   ├── argus-core/
│   │   └── src/argus_core/
│   │       ├── models.py       # 持久化控制面事实
│   │       ├── approvals.py    # 固定审批矩阵与 latest 规则
│   │       ├── state.py        # workstream 状态机
│   │       ├── store.py        # POSIX 锁与原子替换
│   │       ├── promotion.py    # 外部 merge fact 收口
│   │       └── cli.py          # 中文控制面 CLI
│   └── argus-plugin-sdk/
│       └── src/argus_plugin_sdk/
│           ├── contracts.py    # plugin manifest/context/envelope
│           ├── registry.py     # 显式注册，无动态扫描
│           ├── security.py     # SSRF、凭据和大小边界
│           ├── connectors.py   # OpenAPI 参考连接器
│           └── github.py       # GitHub Issues 参考连接器
├── adapters/medusa/            # 目标项目路由与 workstream 声明
├── templates/project/           # 新项目适配器的最小模板说明
└── .agents/skills/             # 项目级 Skill，仍由项目自行维护
```

`uv` workspace 的四个成员版本统一为 `0.2.0`。根包只提供项目共享运行依赖；核心/SDK/adapter 可单独构建为 wheel，发布物包含 Apache-2.0 许可证和各自的 JSON Schema。

## 2. 依赖方向

```text
argus-core  ←  argus-medusa
argus-plugin-sdk  ←  argus-medusa（仅契约复用）
项目级 Skills ──调用 CLI/脚本──> 控制面文件
外部来源 ──只读 fetch──> argus-plugin-sdk SourceEnvelope
```

- `argus-core` 不依赖 SDK、适配器、Skill、模型服务或目标项目。
- `argus-plugin-sdk` 不依赖 core；插件只能返回 `SourceEnvelope`，不能写 iteration 或执行 Skill。
- `adapters/*` 可以依赖 core/SDK，但不能保存真实凭据、接管审批或绕过状态机。
- CLI 只负责 Schema、状态、审批、锁和 promotion；不存在 `run-skill`、模型调用或 Agent 编排命令。
- v1 根目录的项目资产与 0.2 package 是 clean-break 边界，不能通过隐式导入形成兼容层。

## 3. 控制面持久化

`IterationStore(project_root)` 将新文档写入 `.argus/iterations/<iteration-id>/iteration.yaml`。每个 iteration 有独立 lock file：

1. 校验 ID、目录和 lock 路径，拒绝 symlink 目录/lock；
2. 以 `flock(LOCK_EX)` 包住 read-modify-validate-write；
3. 写入同目录临时文件，继承目标权限，`fsync` 后 `os.replace`；
4. 再 `fsync` 父目录；
5. mutator 抛错时不替换原文件。

`iteration.yaml` 只允许 `schema_version: "2.0"`，运行时契约在 `argus_core.models.IterationDocument`，可导出的静态 Schema 在 `argus_core/schemas/iteration.schema.json`，注册表在同目录 `registry.yaml`。

## 4. Workstream 与审批

Web/API workstream 有独立状态和 revision，iteration status 由它们聚合。需求接受必须存在最新 `requirements/accepted/user` 决定；Web 设计、API mapping/cases 和环境必须满足各自最新审批；promotion 审批固定为 user-only。latest 规则意味着新拒绝会覆盖旧接受。

DelegationGrant 需要用户 basis、basis SHA-256、唯一 scope 和有效时间窗。scope 禁止 `requirements` 与 `promotion`；delegated 记录始终是 `actor=agent`，必须带匹配 delegation ID 和非空 note。审批 append 和状态迁移都在同一 Store 事务内完成。

`MergeFact` 必须包含 workstream、GitHub repository、正整数 PR、`release` base、真实格式的 merge SHA、merge time、source URL 和 verified time。每条 workstream 最多一条 fact；只有所有 workstream 都有 fact，iteration 才能变成 `promoted`。

## 5. 来源插件安全

`PluginRegistry` 只接受宿主显式 `register()` 的 manifest/fetch，不扫描模块、不执行来源文本。注册后保存已校验 manifest，插件返回：

- `content` 或 `error` 恰好一个；
- source type 必须在 manifest allowlist；
- envelope 及 content 不能包含 credential-shaped 字段或上下文凭据。

OpenAPI 连接器关闭环境代理，限制 connect/read timeout、重定向次数和总响应字节，并在每个重定向上重新校验公共地址。GitHub 连接器只读 `/repos/{owner}/{repo}/issues`，携带内存 token，过滤 pull request，不创建或更新 issue。

## 6. 验证与发布

核心/SDK/适配器测试位于项目脚本测试层，覆盖 schema、并发、非法迁移、凭据序列化、SSRF/redirect/size、GitHub 分页过滤和 Medusa URL 边界。发布前必须执行：

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest scripts/tests -q
uv build --all-packages
```

测试通过不等于真实频道送达、非作者 PR review、受保护分支合并或真实 merge SHA；这些事实必须由对应外部系统提供。
