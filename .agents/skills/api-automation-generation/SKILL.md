---
name: api-automation-generation
description: 从 exported API cases 与 normalized spec 为 Argus 生成同步 httpx clients、Pydantic request/response models、pytest tests 与 traceability。用于 M7；不得绕过 M4/M5、生成 raw dict client 或修改测试设计。
metadata:
  version: "1.0.0"
---

# Outcome

生成与真实接口 Schema 对齐、可回放、类型化并具有 R→A→nodeid 追踪链的 API 自动化代码。

## Routing

- 只处理 API 分支且 `api/cases.yaml.status=exported` 的 iteration。
- HAR 必须已有 M4/M5 产物；缺少或 stale 时转回 `api-test-design`。
- normalized spec 的 `normalization_warnings[]` 涉及无法恢复的类型时升级给用户，不为其编造类型。

## Inputs / Outputs

- 输入：`api/spec.normalized.yaml`、`api/cases.yaml`、seed registry 与环境契约。
- 输出：`automation/api/{clients,models,tests}/<module>/` 与当前 iteration 的 `traceability.yaml`。
- 测试文件名为 `test_<iteration_id>_<api_case_id>_<behavior>.py`；behavior 是不含 ID、长度不超过 50 的 snake_case 动词短语。

## Steps

1. 读取 PRD §4.6、CODING_STANDARDS API 规则及全部输入；确认当前状态为 `api_cases_exported`，运行 Schema、API coverage、R→A coverage 与 staleness 验证；写文件前记录 `api_cases_exported → api_automation_generating`。
2. 比较输入 hash；未变化且 nodeid 可收集时 no-op。
3. 先搜索并复用同 module 的 clients/models；按 endpoint schema 生成 Pydantic request/response models，保留 required、enum、format、nested object、array、`$ref` 与 combinator 可表达语义。
4. 使用同步 `httpx.Client` 生成类型化 client method；输入和返回值都引用模型，不返回 raw dict，不使用源 Schema 之外的字段。
5. 从 API cases 生成 tests，解析 seed/path/prev_response variables；按 side_effect 标明重跑边界。assertion 位于 tests，client/model 不嵌入业务预期。
6. 每个 test 添加 module、case_id、iteration markers，并以幂等 upsert 写入 A→nodeid traceability。
7. 运行 ruff、pyright、`check_api_models.py`、`check_test_markers.py`、`check_layering.py`、`check_orphan_tests.py`、API coverage 与 A→automation coverage。失败修复并重验最多 3 次。
8. 收集真实 nodeid，验证完整 R→A→nodeid 链，并通过 `../../../scripts/record_event.py` 记录 `api_automation_generating → api_automation_generated`。

## Guardrails

- 不生成 raw dict client、未知字段、猜测类型、硬编码 token/cookie 或绕过 TLS 的默认配置。
- side_effect 为 creates/deletes 的 case 不得自动重复执行，除非先完成 fresh reset。
- 不修改 cases 的 status、expected response、requirements mapping 或 approval/state/event 命名空间。
- 不删除仍被其他 active iteration 引用的 client/model method 或 nodeid；退休必须留有记录并通过 coverage。
- automation 运行时不得读取 `iterations/**`。

## Delivery

报告生成模型与 client method 映射、nodeid、traceability、所有门禁结果及尚未真实请求的接口场景。
