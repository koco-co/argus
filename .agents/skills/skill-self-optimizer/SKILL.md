---
name: skill-self-optimizer
description: 基于 Argus 多 iteration 的真实重复失败证据，提出、确认、应用、验证并版本化项目 Skill 改进。仅在同一 failure pattern 影响至少两个 iteration 或累计至少三次时使用；不得凭单次失败或主观偏好改 Skill。
metadata:
  version: "1.0.0"
---

# Outcome

把量化、可追溯的重复缺陷转化为经用户确认、可回滚且能重新生成旧 iteration 产物的 Skill 版本改进。

## Routing

- 候选只来自 `knowledge/optimization-candidates.yaml`，达到“至少两个 distinct iterations 或至少三次 occurrence”才进入流程。
- 未达阈值时只更新候选证据，不提出 Skill 修改。
- Schema/机器契约变化不是普通 Skill 优化；需要 schema version、迁移说明和 ADR。

## Steps

1. Identify：校验候选的 skill_name、failure_pattern、occurrence_count、affected_iterations 与 evidence_refs，拒绝无法解析的证据。
2. Summarize：概括共同根因、当前 Skill 行为与受影响场景，排除产品缺陷、环境问题和一次性噪声。
3. Propose：把最小 SKILL.md diff 固化到当前 iteration 的 `runs/<run_id>/skill-optimization/proposal.patch`，逐项引用重复实例；同时列出触发、流程、权限、兼容和验收影响。在隔离目录先用 proposed diff 重生成 frozen input，把 frozen baseline 和语义比较结果持久化到对应 Skill 的 `versions/baselines/<version>/`（与 versions snapshot 相邻），并把真实 golden baseline（黄金基线）差异附到提案。
4. Confirm：在写项目规范源前向用户展示完整 diff、证据与真实黄金基线差异；只有明确批准本次 diff 后，才调用 `uv run python scripts/record_approval.py <iteration> --stage skill_change --action approved --artifact iterations/<id>/runs/<run_id>/skill-optimization/proposal.patch` 并继续。
5. Apply：先将旧 `SKILL.md` 保存到 `versions/<previous-version>.md`，再按 SemVer 更新 frontmatter；只应用已批准 diff。
6. Verify：在隔离目录用 1-2 个 frozen input 重新生成，比较 Schema 与语义而非字节；新版本还必须能重新生成旧 iteration 的合法产物。
7. Commit：内容、文案、静态、场景和 golden regression 通过后，创建单一逻辑提交；不得混入无关文件。
8. Push：只推送当前 iteration/工作分支，报告远端结果；不得直接推受保护 release。
9. Resume：恢复触发优化前的主任务，并按 M12 记录已证实的改进结果与回滚路径。

## Guardrails

- 不从模型记忆计数，不伪造 affected iteration、evidence ref、用户批准或 golden 结果。
- 未经用户看到并确认 diff，不修改 Skill；确认一个 diff 不授权后续不同 diff。
- MAJOR 只用于输入/输出 Schema 变化，MINOR 用于向后兼容规则/阶段变化，PATCH 用于文档修正。
- verification 失败立即回滚到 versions snapshot，不以更新 baseline 掩盖回归。

## Delivery

报告候选阈值、证据、批准 diff、版本变化、golden regression、旧 iteration 再生成结果、commit/push 结果与明确回滚文件。
