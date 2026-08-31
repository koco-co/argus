# M9 执行与自调试示例

先在已批准环境中恢复真实靶场，再按当前 iteration 的 traceability 精确选择 nodeid；不得用宽路径混入其他 iteration：

```bash
uv run python scripts/target_app_reset.py
ARGUS_EXECUTED_NODEIDS=reports/executed-first.json TEST_ENV=local \
  uv run pytest $(uv run python scripts/self_debug_helper.py expected-nodeids \
    iterations/2026-08-medusa-api-checkout) \
  -p scripts.pytest_execution_evidence \
  --junitxml=reports/api-junit-first.xml \
  --alluredir=reports/api-allure-first
```

首次失败时，先由 `self_debug_helper.py checkpoint` 固化 attempt 和受影响文件；每次 retry 前按 case 的 `side_effect` 完成可验证 fresh reset，再执行静态验证、受影响模块回归和新的 execution evidence。不要修改断言、预期值、seed 公式或通过 skip/xfail 隐藏失败。

```bash
uv run python scripts/self_debug_helper.py record-ci-auto \
  --iterations iterations \
  --iteration iterations/2026-08-medusa-api-checkout \
  --env local \
  --junit reports/api-junit-first.xml \
  --first-junit reports/api-junit-first.xml \
  --first-executed-nodeids reports/executed-first.json \
  --alluredir reports/api-allure-first \
  --first-alluredir reports/api-allure-first \
  --environment-file config/env.local.yaml \
  --seed-registry shared/testdata/seed-registry.yaml
```

完整 execution manifest、JUnit、Allure、代码 SHA 和环境摘要落盘后，才由唯一状态写入器记录对应终态；真实产品行为不符、认证、5xx、环境不可用等 escalation-only 失败不得进入自动修复循环。
