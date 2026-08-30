# argus-core

Argus 0.2.0 的控制面核心：版本化 Schema、迭代与 workstream 状态、固定审批矩阵、锁内原子写入、中文 CLI 和 promotion 事实校验。

本包不执行 Skill 文本，不调用模型，也不提供 Agent Runtime；测试生成和执行由项目级 Skill 与项目适配器负责。

```bash
uv run argus iteration create checkout-v2 --surface api
uv run argus iteration status checkout-v2
# promotion 只接受独立 verifier 输出的 envelope：
# ARGUS_MERGE_VERIFIER_KEY=<trusted verifier key> \
#   uv run argus promote checkout-v2 --workstream-id api-stream --fact-file verifier-output.yaml
```

v2 文档写入 `.argus/iterations/`，与 v1 `iterations/` 分离且没有迁移命令。静态 Schema 与注册表位于 `src/argus_core/schemas/`。
