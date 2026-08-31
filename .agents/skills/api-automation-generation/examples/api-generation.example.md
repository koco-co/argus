# API 生成示例

从 `api/spec.normalized.yaml` 与 `api/cases.yaml.status=exported` 生成同步 httpx client、Pydantic models 和带 iteration/case markers 的 pytest tests；client 不返回 raw dict，业务断言只来自 canonical API case。

生成前后运行：

```bash
uv run python scripts/lint_test_design.py iterations/demo-api --stage api_cases
uv run python scripts/check_api_models.py --all \
  --spec iterations/demo-api/api/spec.normalized.yaml
uv run python scripts/check_orphan_tests.py
```

每个生成测试的 nodeid 必须回写 `traceability.yaml`。执行时使用 opt-in evidence plugin，不能只凭 JUnit 的总数宣称某个 iteration 通过：

```bash
ARGUS_EXECUTED_NODEIDS=reports/executed-first.json \
  TEST_ENV=ci uv run pytest automation/api -p scripts.pytest_execution_evidence \
  --junitxml=reports/junit-first.xml --alluredir=reports/allure-first
```

发现 A#### 缺少 typed `body_assertions` 或 `derived_oracles` 时，回到 API 测试设计层补齐来源事实；生成器不得在 Python 测试里私自增加未声明的业务 oracle。
