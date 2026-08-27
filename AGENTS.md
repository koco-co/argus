项目状态与开发文档入口：@docs/spec/AGENT_BRIEF.md

## v1.3 强制规则

- 任何确认点必须等待用户明确肯定；`approvals[]` 只能由 `scripts/record_approval.py` 写入，agent 不得手写或伪造 approval。
- v1 只允许一个 branch：`branches.ui=true` 路由至 `functional-test-design`；`branches.api=true` 且 `ui=false` 时，requirements accepted 后停止，不得生成 `test_points.yaml`，改由 `api-test-design` 接管。
- accepted 的上游 YAML 不可直接修改；必须通过 `scripts/reopen_iteration.py` 重开、保留既有 ID，并将下游标记为 `stale`。
- v1 CI 以 GitHub Actions 为唯一权威；自愈只在会话侧运行，CI 只读执行已提交测试。

| 分支声明 | 路由 |
| --- | --- |
| `ui=true, api=false` | `functional-test-design` 完成 M1→M2→M3，再交给 Web automation |
| `ui=false, api=true` | M1 accepted 后停止，不生成 `test_points.yaml`，交给 `api-test-design` 完成 M4→M5 |
| `ui=true, api=true` | v1 非法，必须由 Schema/semantic validation 拒绝 |
