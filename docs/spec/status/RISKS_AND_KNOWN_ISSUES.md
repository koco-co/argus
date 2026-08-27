# Risks & Known Issues

Limitations, instabilities, accepted debts, and rejected proposals. An entry here is a *record*, not an authorization to fix — fixes enter scope only when linked to a Roadmap task.

## Known Limitations, Instabilities & Tech Debt

| # | Issue | Type | Impact | Basis | Handling agreement | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Secrets stored as plaintext in gitignored YAML (`env.*.yaml`, `notify.yaml`) | tech debt (accepted decision) | workstation/backup leak exposure; CI needs secret injection plumbing | PRD §6 explicitly chose lightweight posture | v1 accepted; v2 must migrate to env-var/secret-manager sources; `check_secrets.py` blocks accidental commits only | Accepted debt |
| 2 | Static SQL write-detection is inherently incomplete (dynamic SQL, driver-native calls) | limitation | regex/denylist layers can be evaded by determined or buggy code | review consensus; DB-role is authoritative | treat code layers as defense-in-depth only; real control = SELECT-only DB role (Architecture §6 layer 1) | Accepted |
| 3 | Layering/path scans are AST-level; they cannot prove absence of every devious runtime read of `iterations/**` from automation code | limitation | rare crafted bypasses could couple tests to iteration data | Architecture §3 honest-limits note | residual risk accepted for v1; patterns extended as observed | Accepted |
| 4 | Single long-lived `release` branch contends under parallel iterations | design constraint | merge queues serialize multi-team work | ADR-001 | v1 assumes serial iterations; split branches if parallelism appears | Accepted |
| 5 | `.claude/skills/` symlinks need elevated mode on Windows | limitation | Windows contributors need developer-mode/symlink privileges | review note (Qwen/Kimi) | POSIX-first docs; converters allowed to use directory-copy fallback | Accepted |
| 6 | Self-debug repair quality depends on underlying model capability (evidenced: seven models reviewing this same design produced wildly divergent verdicts) | instability | weaker sessions burn budget without valid repairs; risk of noisy escalations | variance across the archived seven-model review record (consumed 2026-08-27, removed thereafter by owner decision) itself | budgets cap cost; escalation classes stop wrong-direction work; acceptance diff-review is the human backstop | Mitigated-by-design |
| 7 | XMind/xlsx byte-reproducibility pins exporter library versions | maintenance coupling | exporter upgrades may break byte-equality with historical exports | DATA_MODEL conventions | exports are point-in-time artifacts; reproducibility asserted per current lockfile, not retroactively | Accepted |
| 8 | Allure HTML report generation requires the separate allure CLI — no task installs it | known gap | `reports/allure-report/` stays empty; results JSON remains the artifact of record | GLM P2 note | v1 treats allure-results + run-summary as deliverables; HTML gen optional local tooling | Accepted gap |
| 9 | `knowledge/` flat files will degrade at scale | future debt | grep-unwieldy retrieval as entries accumulate | PRD §8 defers categorization deliberately | revisit trigger pre-agreed: categorize once grepping hurts | Deferred |
| 10 | Multi-statement SQL strings are rejected outright by ReadOnlyDBClient (no batch reads) | limitation | an assertion needing several statements makes several calls instead | Architecture §6 | acceptable; keep one statement per query call | Accepted |

## Rejected Review Proposals (recorded so they aren't re-raised as new)

| Proposal (source in the archived seven-model review record, removed 2026-08-27) | Why not adopted |
| --- | --- |
| Hard bandit/container-scan gate on generated code before execution (Kimi) | Heavyweight for single-operator v1; execution already stays inside the operator's project environment. Deferred list captures it as post-v1 hardening. |
| Replace read-only verb allow-list with sqlparse/pglast parsing (Kimi/Grok) | Dependency weight vs benefit; leading-keyword allow-list plus authoritative DB role covers the practical threat model (Architecture §6 rationale). |
| Global cross-repo RTM aggregation service (Gemini) | Post-v1; single repo, file-based traceability suffices now. |
| Numeric SLOs for framework operations ("generation < 30s" etc.) (Kimi NFR) | Arbitrary without measurement history; would be decorative contract numbers. Revisit with real telemetry after Phase 9. |
| Mandatory user confirmation gate after M3 case export (Grok) | Deliberate pipeline trade-off retained; implicit review opportunity documented (PRD §4.3) since M6 invocation is itself a natural pause the user controls. |
| Coverage quota percentages for framework's own test suite (various) | Replaced by fixture-pair completion rules (TESTING_STRATEGY coverage section). |

## Open Questions

| Question | Affects | Known so far | Needs deciding |
| --- | --- | --- | --- |
| Exact Medusa version/pin set | Phase 5 lockfile | backend+storefront starters move fast; corrections logged in ADR-002 | pin values chosen at execution time against stable tags |
| CI runner sizing for harness (compose in GH Actions) | Phase 7 e2e job budget | postgres+redis+backend+storefront stack is nontrivial per-run | measure one run; consider self-hosted or scheduled-only e2e if minutes cost excessive |
| Final secret enumeration for `env.ci.yaml` assembly | Phase 7 secrets wiring | base_url, store key, admin creds, optional DSN | confirm minimal set while implementing 5.x fixtures |
