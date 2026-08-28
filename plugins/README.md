# plugins/

Fetch + normalize layer between external sources and the skill layer
(ARCHITECTURE §1). A plugin resolves a source ref into a normalized
**source payload envelope**, persisted to disk by `scripts/run_plugin.py`
*before* schema validation — never in-memory handoff, never case-design
logic, never LLM calls inside a plugin (ADR-006).

- `_interface/contract.md` — envelope rules (authored in Roadmap 2.1)
- `_interface/schemas/` — `*_source_payload.schema.json` (DATA_MODEL §10)
- `requirement-sources/` / `api-sources/` — connector placeholders (post-v1)

Registration: `registry.yaml` is the only name→plugin lookup.

## v1 运行入口

先用 `scripts/new_iteration.py` 创建迭代，再导入已有信封：

```sh
uv run python scripts/run_plugin.py --payload <信封.yaml> --iteration iterations/<id>
```

未来注册的连接器使用 `uv run python scripts/run_plugin.py <name> <source_ref> --iteration iterations/<id>`。注册项包含 `name`、相对 `plugins/` 的 Python 文件 `path`、`source_type`，以及可选的 `credentials_env`（凭据名到环境变量名的映射）。注册表不能有重复名称，路径不能越出插件目录；v1 的 `plugins: []` 保持为空，测试中的临时插件不属于产品连接器。

运行器在子进程调用 `fetch(source_ref, *, credentials)`，总时限为连接默认值 5 秒与读取默认值 30 秒之和；未来连接器仍须在实际 HTTP 客户端分别执行这两个超时，并检查每次重定向和实际连接地址。入口会拒绝解析至非公网的 URL，但该预检不是防 DNS 重绑定的网络沙箱，不能替代连接器与主机侧控制。

输出信封及导入文件的大小上限为 8 MiB；`.gz` 输入同时限制压缩前后的大小。插件日志不直接输出，异常转换为结构化失败信封；注册凭据不得回流到载荷。已有隔离文件内容不同则拒绝覆盖，内容相同只重验不重写。成功退出只表示信封合法；错误变体即使 Schema 合法也返回失败，之后必须由 M1/M4 判断来源可用性。
