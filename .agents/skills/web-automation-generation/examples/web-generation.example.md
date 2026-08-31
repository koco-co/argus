# Web 生成示例

从 `functional-cases.yaml.status=exported` 生成按 `module` 放置的 Page Object、fixture 和 pytest test；测试文件中的 `pytest.mark.iteration`、`case_id` 与 `traceability.yaml` 必须逐字一致。

执行前先收集精确 nodeid，执行插件把每个 attempt 的 outcome 留存为证据：

```bash
ARGUS_EXECUTED_NODEIDS=reports/executed-first.json \
  TEST_ENV=ci uv run pytest automation/web -p scripts.pytest_execution_evidence \
  --junitxml=reports/junit-first.xml --alluredir=reports/allure-first
uv run python scripts/self_debug_helper.py record-ci-auto \
  --iterations iterations \
  --iteration iterations/demo-checkout \
  --junit reports/junit-first.xml \
  --executed-nodeids reports/executed-first.json \
  --first-junit reports/junit-first.xml \
  --first-executed-nodeids reports/executed-first.json \
  --alluredir reports/allure-first --first-alluredir reports/allure-first \
  --commit-sha "$(git rev-parse HEAD)" --env ci
```

`side_effect=creates|deletes` 的 case 不能被无 reset 的 retry 重放；真实靶场必须 fresh reset，manifest 必须绑定 expected、executed、JUnit/Allure 摘要和当前代码 SHA。
