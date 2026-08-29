# release 分支保护验收证据（2026-08-28）

仓库：`koco-co/argus`

## 已核实事实

- `release` 从远端 `main` 的 `c51649fe0e05db9c71077eec33773d114ceaf5d2` 创建。
- 必需状态检查：`static-checks`、`e2e`；`strict=true`，合并前必须与目标分支同步。
- 必需人工批准数：1；启用 stale review 驳回与最后推送者不得批准。
- 管理员同样受保护；要求线性历史与对话解决；禁止强推和删除分支。
- 在本证据的初始快照中，PR #1 已转为 Ready，并在提交 `b0529d1` 真实运行且通过 `static-checks`、`changes` 与 `e2e`；当时仍缺少受保护分支要求的非作者批准，不把阶段性绿灯当作最终迭代验收。

## 负向验收

从 `codex/complete-v1` 直接执行 `git push origin HEAD:release`，GitHub 返回 `GH006 Protected branch update failed`，明确要求通过 Pull Request，远端 `release` 未被修改。

## 可复核命令

```bash
gh api repos/koco-co/argus/branches/release/protection
gh pr checks 1
git ls-remote origin refs/heads/release
```

## 2026-08-29 交付更新

按用户明确要求，PR #1 的目标从 `release` 改为默认分支 `main`，随后由 GitHub 真实合并，merge SHA 为 `f7fb82a5196aa665f47cdf22928b5bd7c2887f07`；PR #9 的订单确认时序 POM 修复随后也由 GitHub 真实合并，代码 merge SHA 为 `88f2b6abce9dfa5ded57db3191609f891fd3eed4`；PR #10 文档更新再度真实合并，当前 `main` HEAD 为 `aec57829a3fecd57b77d59c1ca73a175346c6215`。`main` 当前未配置分支保护；上述合并没有改写受保护的 `release`，其远端 SHA 仍为 `c51649fe0e05db9c71077eec33773d114ceaf5d2`。因此本更新记录的是 `main` 交付事实，不替代 7.5、7.6 或 Phase 9 所要求的受保护 `release` 合并与收口。
