# Environment Setup (Target-State)

Prerequisites, initialization steps, and every operational command the framework will expose. **Status honesty**: this repo contained documentation only until 2026-08-27, when Roadmap Phase 0 (tasks 0.1–0.8) was implemented and verified — `pyproject.toml`, `uv.lock`, `.python-version`, `Makefile`, `.gitignore`, `.pre-commit-config.yaml`, the directory skeleton, `scripts/new_iteration.py` + `iteration.schema.json` + registry, and the four local pre-commit hook stubs now exist. Commands below flip from "已定义" to "已运行 (date)" only after an actual recorded run; later-phase scripts (`validate_schema.py` real logic, exporters, checkers, harness) are stubs or absent until their Roadmap tasks land.

## Prerequisites

最近真实自检见 [2026-08-28 Step 0 证据](../status/STEP0_CHECK_2026-08-28.md)：Docker/Compose、uv/Python 3.12、项目 Chromium 启动及 GitHub/Actions 访问已检查。真实 webhook 尚无验证证据；按用户最新要求，该缺项在 Phase 7 首个实际依赖它的 DoD 前列为非阻塞待办，不提前阻塞开发。本次自检不等于靶应用启动、生成测试、M8 配置、通知送达或最终验收通过，也不改变下表历史命令状态。当前执行口径见 [AGENT_BRIEF](../AGENT_BRIEF.md)。

| Requirement | Version / note | Why |
| --- | --- | --- |
| uv | current stable | project/env management |
| Python | 3.12.x (`.python-version` pin) | language baseline |
| Docker + compose v2 | for target-app harness | Medusa stack (backend, Postgres, Redis) runs in its own containers |
| Playwright browsers | **Chromium only** (v1 decision; Firefox/WebKit installs are not performed) | single validated browser matrix |
| Network access to PyPI + GitHub Actions runners | build time only | dependency sync, CI |

Secrets policy: real values (`config/env.local.yaml`, `notify.yaml`) are gitignored and provided by the user at M8; placeholders everywhere else use obvious fakes (`CHANGE_ME`). No credentials may appear in docs/examples. **CI injection rule**: secrets travel as workflow `env:` variables mapped from `${{ secrets.* }}` — never as shell arguments, never via inline `echo` (command tracing would leak them). `settings.py` reads env-var overrides with the same shape as the YAML keys, so most CI jobs never need a secrets file; when one is required, `settings.py assemble --env ci` writes the gitignored `config/env.ci.yaml` in-process.

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
| Clone + toolchain check | repo root | `uv --version && docker info` | both succeed | 已运行 2026-08-27（uv ✓；docker 未验证 — Phase 0 无靶应用步骤，Phase 5 前置） |
| Project init | root | create `pyproject.toml`, `uv python pin 3.12` then `make setup` | creates `.venv`, installs deps + chromium + hooks | 已运行 2026-08-27（fresh-clone 验收通过；本机 playwright 下载需绕过系统代理，见 CHANGELOG） |
| Scaffold iteration | root | `make new-iteration ID=test-fixture-001` | builds full `iterations/<id>/` tree incl. `iteration.yaml`; second same-ID call errors unless `--force` | 已运行 2026-08-27（BRANCH=ui\|api 声明分支；测试覆盖重复/ID/单迭代规则） |
| Target app up | root | `make target-app-up && make target-app-healthcheck` | pinned compose + version lockfile must exist first | 待实现 (harness task, pre-Phase-5) |

## Development & Verification Commands

| Purpose | Directory | Command | Expected result | Status |
| --- | --- | --- | --- | --- |
| Lint | root | `make lint` | clean on skeleton and after generation | 已运行 2026-08-27（ruff + pyright 零告警） |
| Framework tests | root | `uv run pytest scripts/tests` | integration+unit suites green incl. fixture round-trips and DATA_MODEL JSON-block parsing | 已运行 2026-08-27（43 passed；Phase 0 范围 = scaffolder + 结构 diff；DATA_MODEL 块解析测试属 1.1） |
| Schema validation | root | `make validate-iteration ID=<id>` | exit 0 valid / non-zero naming exact violating field | 已定义 / 待实现（`validate_schema.py` 目前为 0.3 桩，1.2 落地） |
| Coverage gate | root | `uv run python scripts/check_coverage.py --tier from-iteration iterations/<id>` | branch/state-selected tier verdict per PRD §5.1; `auto` is local audit only | 已运行 2026-08-28（1.17 验收；无参形态评估全部迭代，CI 采用） |
| Static all-gates | root | `uv run pre-commit run --all-files` | green on compliant tree; red on any broken schema, state, boundary, or secret fixture (patch-scope fixtures run with framework tests) | 已运行 2026-08-27（骨架绿：ruff 实际执行；四个本地钩子按 0.3 为 no-op 桩） |
| Generated regression (UI) | root | `make web-tests MODULE=checkout ENV=local` | suite green against healthy harness | 已定义 / 待实现 |
| Export artifacts | root | `make export ID=<id>` | byte-reproducible `.xmind`/`.xlsx`/`.md` written under `exports/` | 已定义 / 待实现 |
| Run evidence archive | root | `uv run python scripts/self_debug_helper.py archive --run-id <rid>` | summary/allure/logs copied into `iterations/<id>/runs/<rid>/`, previous runs untouched | 已定义 / 待实现 |
| CI equivalent | CI | static-checks on every PR; e2e on release PRs or `automation/**`/`iterations/**` changes; SHA-pinned actions, minimal permissions, timeouts/concurrency; both notify under `always()` and upload per-run evidence dirs | see ARCHITECTURE §8 | 已定义 / 待实现 |

Verification discipline: each command flips its status to "已运行 (date + evidence link)" in this table only after an actual recorded run during development.
