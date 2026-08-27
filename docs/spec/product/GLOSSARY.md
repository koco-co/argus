# Glossary

Single source of truth for domain terms, ID formats, and naming rules. Other documents reference this page instead of redefining the same concept.

## Domain Terms

| Term | Definition | Scope | Confusable concepts / aliases | Basis |
| --- | --- | --- | --- | --- |
| **Iteration** | One time-boxed unit of work: a raw requirement flows through clarification, test design, (optionally) API case design, automation generation, execution, acceptance, and merge. Everything formal about one iteration lives under `iterations/<iteration_id>/`. | Whole framework | "release", "sprint", "run" | PRD §2, §5 |
| **Module** | A business feature area (e.g. `checkout`, `auth`) used to organize cases, page objects, and generated tests. Not a Python package concept. | Case design + `automation/` tree | Python module/package | PRD §4.3, Architecture §2 |
| **Confirmation point** | A pipeline stage where the agent must stop and obtain explicit user acceptance before advancing. Only M1 (clarify + accept), M2 (accept), M8 (env values), and M13 (skill edit) have them. | Pipeline contract | "review" (non-blocking reads) | PRD §3–4 |
| **Schema-gated** | An output is not final until `scripts/validate_schema.py` passes against its JSON Schema. Skills, pre-commit, and CI call the same validator. | Data flow across layers | lint pass (ruff/pyright are separate gates) | Architecture §1, §4 |
| **Self-debug loop** | M9's autonomous fix-and-rerun cycle. Budget-bounded; the user is contacted only at terminal states (`passed` / `budget_exceeded` / escalated failure class). | Execution phase | generic "retry" (pytest `-n` reruns, flaky plugins) | PRD §4.7 |
| **Patch (self-debug)** | Any file modification made by the self-debug loop between runs. Restricted to `automation/**` implementation code; assertions, expected values, and everything outside `automation/` are frozen. | Execution phase | git diff shown to user at acceptance | PRD §4.7, CODING_STANDARDS |
| **Failure class** | Taxonomy attached to every failed attempt (`locator_drift`, `timing`, `fixture_error`, `serialization_error`, `import_type_error`, `data_issue`, `environment_unavailable`, `auth_failure`, `backend_5xx`, `product_behavior_mismatch`, `requirement_conflict`). Determines whether auto-fix is permitted or the loop escalates. | Self-debug + reporting | `failure_type` (unused alias — do not introduce) | PRD §4.7 |
| **Source payload** | The normalized dict/YAML produced by a plugin (or hand-fed equivalent), validated against a *source* schema (`requirement_source_payload` / `api_source_payload`). Converted by M1/M4 into internal workflow artifacts. Plugins do **not** emit internal artifacts directly. | Plugin interface | internal artifacts like `requirements.yaml` | PRD §3 M14, Architecture §3 |
| **Derived view** | Human-readable render (`.md`, `.xmind`, `.xlsx`) generated deterministically from a YAML source by scripts. Never hand-edited, never authored freeform by the LLM. | Exports | source-of-truth YAML files | ARCHITECTURE §2; layout provenance ADR-007 |
| **Stale artifact** | A generated artifact whose recorded upstream input hash (`generated_from.sha256`) no longer matches the upstream file. Stale artifacts fail validation and cannot be merged. | Consistency management | "conflicted" (git term) | PRD §6, DATA_MODEL |
| **Coverage tier** | The depth a requirement has reached: `test_point_covered` (R→T), `case_covered` (T→C), `automated` (C→nodeid). Which tier CI demands depends on the iteration's own stage — see PRD §5.1, enforced by `check_coverage.py`. | M10 / CI gate | naive "100% coverage" (undefined without tiers) | PRD §5.1, Architecture §4.5 |
| **Automation-required flag** | Boolean on a requirement (`automation_required`, default `true`). `false` marks manual-by-design requirements, which must carry `manual_reason` and are excluded from the `automated` tier gate. | M2–M10 | old hand-written `coverage_status` (removed in v1.1 — now derived) | PRD §4.2, DATA_MODEL |
| **Skill** | An agent instruction package under `.agents/skills/<name>/` (SKILL.md + schemas + examples). Guides agent decisions; contains no importable Python entrypoint. `.claude/skills/<name>` symlinks exist only as a Claude Code adapter. | Agent layer | Python CLI tools under `scripts/` | Architecture §1–2 |
| **Script** | A deterministic Python tool under `scripts/` invoked via `uv run python scripts/<name>.py`. No LLM calls. Exports, validators, checkers, and runners live here. | Toolchain | Skills (above) | Architecture §1, Roadmap Phase 0–1 |

## ID & Naming Formats

All persisted YAML carries a top-level `schema_version: "1.0"`. Status enums are **lowercase snake_case** in files; documents may capitalize them in prose for readability, but parsers only ever match the lowercase forms.

| Object | Format & valid example | Generation rule | Uniqueness scope | Basis |
| --- | --- | --- | --- | --- |
| `iteration_id` | kebab-case slug, e.g. `2026-08-medusa-checkout-flow`; regex `^[a-z0-9][a-z0-9-]*$` | Created only by `scripts/new_iteration.py` (second call with same ID errors; `--force` requires re-confirmation) | Repo-global; branch name `test/<iteration_id>` derives from it | Roadmap 0.7 |
| `requirement_id` | `^R[0-9]{4}$`, e.g. `R0007` | Allocated sequentially within the iteration by test-design stage 1 | Unique within its iteration; IDs are stable once allocated and never reused after deletion | PRD §4.1 |
| `test_point_id` | `^T[0-9]{4}$` | test-design stage 2, sequential | Within its iteration | PRD §4.2 |
| `case_id` (functional) | `^C[0-9]{4}$` | test-design stage 3 | Within its iteration. Cross-iteration identity is the pair `(iteration_id, case_id)`; `traceability.yaml` and pytest markers always carry both | PRD §4.3, GLOSSARY (this rule adopted from review) |
| `api_case_id` | `^A[0-9]{4}$` | api-test-design | Within its iteration | PRD §4.4 |
| `automation_test_id` | Pytest nodeid relative to repo root, e.g. `automation/web/tests/checkout/test_guest_checkout.py::test_discount_code_reduces_total` | Assigned by web/api-automation-generation; recorded verbatim in `traceability.yaml` | Repo-global (tests live outside iterations/) | Architecture §4.5 |
| `run_id` | `^run-[0-9]{8}T[0-9]{6}Z(-[a-z0-9]{4})?$`, e.g. `run-20260827T101500Z-a3f2` (UTC timestamp + short random suffix on collision) | Created by the self-debug runner at suite start | Unique per execution within its iteration | PRD §2.1, §4.7 |
| `module` (name) | Regex `^[a-z][a-z0-9_]*$`, e.g. `checkout` | First introduced by whichever stage needs it (case tag or API spec); reused thereafter, never aliased | Repo-global namespace shared by case tags, POM directories, and API clients | Architecture §2, CODING_STANDARDS |
| Module tag | Tag literal `module:<name>` where `<name>` matches the module format above | Required on every functional case; must equal the case's owning module | Exactly one `module:` tag per case | PRD §4.3 |
| Marker set | `@pytest.mark.module("<name>")`, `@pytest.mark.case_id("<id>")`, `@pytest.mark.iteration("<id>")` on every generated test | Written by generation skills; metadata only — **module selection for runs is done by directory**, not marker expressions | Markers must agree with file location; checked by `check_test_markers.py` | PRD §4.5, Roadmap 1.x |
| Export filenames | `<Project>_v<N>_Cases.xmind`, `<Project>_v<N>_API_Cases.xlsx` | `<Project>` = repo name; `<N>` = integer version taken from the highest existing `<N>` in the same `exports/` dir + 1 (starting at 1); exporters overwrite nothing | Per-iteration exports/ directory | Architecture §2, Roadmap 1.4–1.5 |
| Skill versions | SKILL.md frontmatter carries `version: X.Y.Z`; optimizer bumps version and records previous copy under `.agents/skills/<name>/versions/` | skill-self-optimizer only, after user confirmation | Repo-global per skill name | Roadmap 8.2, KIMI-review adoption |
