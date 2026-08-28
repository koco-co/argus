# 版本快照

首次发布为 1.0.0。后续经批准的变更在应用前保存旧版 SKILL.md 与回滚说明。四个生成 Skill 的冻结输入和语义期望位于各自 `versions/baselines/<version>/`，统一由 `scripts/check_skill_golden.py` 校验；不得把更新黄金期望当成修复回归。

当前 1.1.0 入口的 1.0.0 原文快照为 `versions/1.0.0.md`；下一次优化必须连同 proposal、golden 差异和 rollback 证据保存。
