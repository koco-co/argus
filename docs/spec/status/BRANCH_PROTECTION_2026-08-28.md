# release 分支保护验收证据（2026-08-28）

仓库：`koco-co/argus`

## 已核实事实

- `release` 从远端 `main` 的 `c51649fe0e05db9c71077eec33773d114ceaf5d2` 创建。
- 必需状态检查：`static-checks`、`e2e`；`strict=true`，合并前必须与目标分支同步。
- 必需人工批准数：1；启用 stale review 驳回与最后推送者不得批准。
- 管理员同样受保护；要求线性历史与对话解决；禁止强推和删除分支。
- PR #1 已真实运行并通过 `static-checks`、`changes` 与 `e2e`。该 PR 仍为 Draft，不把阶段性绿灯当作最终迭代验收。

## 负向验收

从 `codex/complete-v1` 直接执行 `git push origin HEAD:release`，GitHub 返回 `GH006 Protected branch update failed`，明确要求通过 Pull Request，远端 `release` 未被修改。

## 可复核命令

```bash
gh api repos/koco-co/argus/branches/release/protection
gh pr checks 1
git ls-remote origin refs/heads/release
```
