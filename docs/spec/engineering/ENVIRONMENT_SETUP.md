# Environment Setup (Target-State)

Prerequisites, initialization steps, and every operational command the framework exposes. **状态诚信**：截至 2026-08-28，Schema/状态/覆盖/边界/只读/密钥门禁、XMind/XLSX/Markdown 导出、Medusa 靶场、UI/API 生成样例、M9 自调试证据与 GitHub Actions 已实际运行；表中仍标为人工门禁的项目不得由这些机器证据代替。命令只有在真实运行并留下可复核结果后才标记“已运行”。

## Prerequisites

最近真实自检见 [2026-08-28 Step 0 证据](../status/STEP0_CHECK_2026-08-28.md)：Docker/Compose、uv/Python 3.12、项目 Chromium 启动及 GitHub/Actions 访问已检查。真实 webhook 尚无验证证据；按用户最新要求，该缺项在 Phase 7 首个实际依赖它的 DoD 前列为非阻塞待办，不提前阻塞开发。本次自检不等于靶应用启动、生成测试、M8 配置、通知送达或最终验收通过，也不改变下表历史命令状态。当前执行口径见 [AGENT_BRIEF](../AGENT_BRIEF.md)。

| Requirement | Version / note | Why |
| --- | --- | --- |
| uv | current stable | project/env management |
| Python | 3.12.x (`.python-version` pin) | language baseline |
| Docker + compose v2 | for target-app harness | Medusa stack (backend, Postgres, Redis) runs in its own containers |
| Playwright browsers | **Chromium only** (v1 decision; Firefox/WebKit installs are not performed) | single validated browser matrix |
| Network access to PyPI + GitHub Actions runners | build time only | dependency sync, CI |

Secrets policy: real values (`config/env.local.yaml`, `notify.yaml`) are gitignored and provided by the user at M8; placeholders everywhere else use obvious fakes (`CHANGE_ME`). No credentials may appear in docs/examples. `base_url` 是浏览器站点地址；组合 UI/API 执行时可用 `api_base_url` 指定独立后端地址。**CI injection rule**: secrets travel as workflow `env:` variables mapped from `${{ secrets.* }}` — never as shell arguments, never via inline `echo` (command tracing would leak them). `settings.py` reads env-var overrides with the same shape as the YAML keys（包括 `ARGUS_BASE_URL` 与可选 `ARGUS_API_BASE_URL`）, so most CI jobs never need a secrets file; when one is required, `settings.py assemble --env ci` writes the gitignored `config/env.ci.yaml` in-process.

## Planned Base Configuration (authored in Phase 0)

Authoritative skeletons to be created verbatim-shaped in Phase 0 tasks:

**pyproject.toml** — core deps: pytest≥8.3, pytest-playwright≥0.5, pytest-xdist≥3.6, **allure-pytest**≥2.15 (v1.0's `pytest-allure-adapter` does not exist on PyPI), httpx≥0.27, pydantic≥2.9, rich≥13.9, pyyaml≥6.0, jsonschema≥4.23, **rfc3339-validator≥0.1.4** (added 2026-08-28: without it jsonschema's `date-time` FormatChecker is a silent no-op, contradicting DATA_MODEL's validator mandate; see CHANGELOG), openpyxl≥3.1 (xlsx round-trip needs it). Optional groups (moved out of core per review): `[dependency-groups] dev=[ruff, pyright, pre-commit]`, `mobile=[appium-python-client]`, `perf=[locust]`. Tool tables: pytest markers with `--strict-markers`, ruff select `E,F,I,UP,B,SIM` line-length 100, pyright basic.

**pre-commit hooks**: ruff/ruff-format remote hooks; local hooks `validate-schema` (entry `scripts/validate_schema.py`, matches registered artifacts plus the exact `iterations/*/00-raw/source-payload.yaml` path; unrelated raw inputs aren't schema artifacts), `validate-iteration-state` (`validate_iteration.py`), `no-db-writes`, `check-secrets`.

**Makefile targets** (v1.0 renames applied):

```makefile
setup:            uv sync && pre-commit install && playwright install chromium
new-iteration ID=:  uv run python scripts/new_iteration.py $(ID)
validate-iteration ID=:  uv run python scripts/validate_schema.py iterations/$(ID)   # renamed from gen-cases
export ID=:       export_xmind + export_xlsx + render_md for iterations/$(ID)
web-tests MODULE=:   TEST_ENV=$(ENV) uv run pytest automation/web/tests/$(MODULE) --alluredir=reports/allure-results
api-tests MODULE=:   TEST_ENV=$(ENV) uv run pytest automation/api/tests/$(MODULE) --alluredir=reports/allure-results
lint:             uv run ruff check . && uv run pyright
target-app-up/seed/reset/healthcheck/down:  harness scripts (policy: TESTING_STRATEGY harness section)
```

Notes vs v1.0: module selection is by **path**, not `-m` marker expressions (pytest cannot filter parameterized marks that way — reviewed & confirmed error); no `debug` target exists (self-debug is the agent-session flow, ADR-004). Execution scratch (`--alluredir=reports/allure-results`) stays gitignored display-only state; the durable evidence copy lands in `iterations/<id>/runs/<run_id>/` via the self-debug helper / CI archive step (ADR-010).

**.gitignore essentials**: gitignored env/notify YAMLs; `reports/**` + `!reports/**/.gitkeep`; `automation/api/har/**` + keeper; `config/env.ci.yaml`; `.venv/`. Run evidence (ADR-012): under `iterations/*/runs/*/`, `run-summary.yaml` and patch files stay tracked while `allure-results/`, `logs/`, `traces/` are ignored (`iterations/*/runs/*/allure-results/**` etc., each with keeper-free full-ignore rules). Raw inputs: tracked text under `iterations/*/00-raw/` (subject to secret scan), binaries/large-file patterns ignored there with manifest fallback (PRD §6).

## Installation & Initialization

| Step | Directory | Command | Precondition / effect | Status |
| --- | --- | --- | --- | --- |
| Clone + toolchain check | repo root | `uv --version && docker info` | both succeed | 已运行 2026-08-28（uv 与 Docker 均通过，Compose 靶场已完成全新 build/up/down/re-up） |
| Project init | root | create `pyproject.toml`, `uv python pin 3.12` then `make setup` | creates `.venv`, installs deps + chromium + hooks | 已运行 2026-08-27（fresh-clone 验收通过；本机 playwright 下载需绕过系统代理，见 CHANGELOG） |
| Scaffold iteration | root | `make new-iteration ID=test-fixture-001` | builds full `iterations/<id>/` tree incl. `iteration.yaml`; second same-ID call errors unless `--force` | 已运行 2026-08-27（BRANCH=ui\|api 声明分支；测试覆盖重复/ID/单迭代规则） |
| Target app up | root | `make target-app-up && make target-app-healthcheck` | pinned compose + version lockfile must exist first | 已运行 2026-08-28（全新 build/up、连续健康探测、down 清场与再次全新 up 均通过） |

## Development & Verification Commands

| Purpose | Directory | Command | Expected result | Status |
| --- | --- | --- | --- | --- |
| Lint | root | `make lint` | clean on skeleton and after generation | 已运行 2026-08-27（ruff + pyright 零告警） |
| Framework tests | root | `uv run pytest scripts/tests` | integration+unit suites green incl. fixture round-trips and DATA_MODEL JSON-block parsing | 已运行 2026-08-28（401 项；含批准产物摘要完整性、CLI 入口、通知信封、非空 job 状态与无 JUnit 降级、CI 强制失败/flaky 调度、PR 覆盖范围选择、环境化 API 地址、目录权威、导出跨秒确定性、UI/API 反向闭包、M9 四类终态、数据库只读角色与周回归 issue 升级） |
| Schema validation | root | `make validate-iteration ID=<id>` | exit 0 valid / non-zero naming exact violating field | 已运行 2026-08-28（目录递归展开 10 个 UI 工件通过；非法 fixture 仍精确报 JSON 路径） |
| Coverage gate | root | `uv run python scripts/check_coverage.py --tier from-iteration iterations/<id>` | branch/state-selected tier verdict per PRD §5.1; `auto` is local audit only | 已运行 2026-08-28（单 iteration、全量及 `--changed-base` PR 范围均通过；iteration 工件只选对应目录，自动化/共享门禁变化保守检查全部，删除 iteration 明确失败） |
| Static all-gates | root | `uv run pre-commit run --all-files` | green on compliant tree; red on any broken schema, state, boundary, or secret fixture (patch-scope fixtures run with framework tests) | 已运行 2026-08-28（ruff、format、Schema、状态、DB 只读、密钥共 6 个真实钩子通过；CLI 静默空跑有回归门禁） |
| Generated regression (UI) | root | `make web-tests MODULE=checkout ENV=local` | suite green against healthy harness | 已运行 2026-08-28（Medusa 折扣正向/负向，Chromium 与双 worker 通过） |
| Generated regression (API) | root | `make api-tests MODULE=checkout ENV=local` | typed client/model suite green against healthy harness | 已运行 2026-08-28（Store API 促销正向/非法载荷负向，双 worker 通过） |
| Harness parallel smoke | root | `ARGUS_RUN_ID=smoke TEST_ENV=local uv run pytest -n 2 automation/web/tests/harness` | gw0/gw1 均执行，worker 会话和命名空间隔离 | 已运行 2026-08-28（连续三轮全绿；PROD collect 另验证 1 项非只读探针被剔除） |
| Environment check | root | `uv run python shared/config/settings.py check --env local --iteration iterations/<id>` | 全部必需键、URL/DSN 与只读声明合法后才允许 M8 approval | 已运行 2026-08-28（完整/破损/API/UI/空 YAML 夹具均通过预期；本地真实 UI/API fixture 配置均通过，文件权限为 `0600`） |
| Export artifacts | root | `make export ID=<id>` | branch-aware byte-reproducible `.xmind` or `.xlsx`, plus `.md`, written under `exports/` | 已运行 2026-08-28（UI/API 各连续两次 SHA-256 一致；XLSX 的 ZIP 与 core modified 时间均固定） |
| Run evidence archive | root | `uv run python scripts/self_debug_helper.py archive iterations/<id>/runs/<rid> reports/allure-results reports/logs` | display reports copied into the named run without overwrite | 已运行 2026-08-28（Playwright trace 与五轮 JUnit 日志归档；重复目标拒绝覆盖） |
| CI equivalent | CI | static-checks on every PR; e2e on release PRs or `automation/**`/`iterations/**` changes; SHA-pinned actions, minimal permissions, timeouts/concurrency; both notify under `always()` and upload per-run evidence dirs | see ARCHITECTURE §8 | 已运行 2026-08-28（PR #1 的 static-checks/e2e 已真实通过；最新提交继续由同名必需检查验证） |
| CI 对抗场景 | GitHub Actions | 手工调度 `static-checks(force_failure=true)`；手工调度 `e2e(acceptance_scenario=force_failure\|force_flaky)` | 失败分支执行失败通知且保持失败；flaky 首轮失败、仅重跑一次并分类 `flaky-suspect`；证据上传与 down 仍执行 | 本地控制探针已验证首轮失败/次轮通过及持续失败；远端调度在工作流提交后执行 |

Verification discipline: each command flips its status to "已运行 (date + evidence link)" in this table only after an actual recorded run during development.
