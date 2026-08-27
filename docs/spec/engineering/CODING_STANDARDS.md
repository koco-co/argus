# Coding Standards

Conventions for all code this project produces: enforcement scripts, generated automation assets, and patches made by the self-debug loop. Tool-enforced rules vs human/agent conventions are separated below. Status: design-stage conventions agreed during doc consolidation; they bind the moment the corresponding files exist (Roadmap Phase 0–1).

## Tools & Rule Sources

| Tool | Scope | Notes |
| --- | --- | --- |
| ruff (+ ruff-format) | all Python | line-length 100; select `E,F,I,UP,B,SIM`; wired via pre-commit + Makefile `lint` |
| pyright (`basic`) | all Python | type-check gate next to ruff |
| pytest (`--strict-markers`) | scripts/tests + automation suites | custom markers declared once in root conftest |
| jsonschema checks | iteration/artifact YAMLs | DATA_MODEL contracts |
| Project checkers | boundaries listed in Architecture §5 | POM boundary, API models, markers, layering, DB read-only, secrets |

## Naming & Organization

| Object | Convention | Example | Basis |
| --- | --- | --- | --- |
| Page/screen object class | `<Name>Page`, one per route/screen, under `pages/<module>/` | `automation/web/pages/checkout/checkout_page.py::CheckoutPage` | ADR-none; Arch §5 rule retained |
| Locator accessors | private methods, leading underscore, return Playwright locators — never exposed strings | `_discount_input()` | below |
| Action methods | public, verb-named, return `self` or a **value**; no assertions inside | `apply_discount_code(code) -> CheckoutPage` | below |
| Shared widgets | `components/`, composed into page objects, never copy-pasted between pages | navbar, modal | Reuse-before-create rule |
| Generated tests | `test_<behavior>.py` under `tests/<module>/`; folder IS the module selector | `tests/checkout/test_guest_checkout.py` | run selection by directory (review fix) |
| Markers | exactly `module(<name>)`, `case_id("<id>")`, `iteration("<id>")`; metadata only, consistency checked by script | see Architecture §5 | GLOSSARY |
| API clients/modules | `clients/<module>/` httpx wrapper classes; `models/<module>/` pydantic models, one request+response pair minimum per endpoint used | `automation/api/clients/orders/orders_client.py` | PRD §4.6 |
| Shared utilities | lowercase module names under `shared/<area>/`; DB access exclusively through `shared/db/readonly_client.py` | `shared/assertions/db_asserts.py` | Architecture §6 |
| Scripts | single-purpose CLIs under `scripts/`, no LLM calls, stdlib-project deps only | `scripts/check_coverage.py` | GLOSSARY "Script" |

## Canonical Patterns

### Page object (web)

```python
class CheckoutPage:
    """Encapsulates the checkout route. No assertions. No test logic."""

    def __init__(self, page: Page):
        self._page = page

    def _discount_input(self):                      # locators stay private
        return self._page.get_by_label("Discount code")

    def apply_discount_code(self, code: str) -> "CheckoutPage":
        self._discount_input().fill(code)
        self._page.get_by_role("button", name="Apply").click()
        return self

    def get_total(self) -> str:                     # value-returning read
        return self._page.get_by_test_id("order-total").inner_text()
```

```python
@pytest.mark.module("checkout")
@pytest.mark.case_id("C0012")
@pytest.mark.iteration("2026-08-medusa-checkout-flow")
def test_discount_code_reduces_total(page, checkout_seeded):
    checkout_page = CheckoutPage(page)
    checkout_page.apply_discount_code(SEED["discount_code"])
    assert checkout_page.get_total() == checkout_seeded.expected_discounted_total
```

Expected values come from the **seed context** (`checkout_seeded` computes the discounted total from seeded prices) — never hardcoded literals copied from case descriptions, so environment drift cannot masquerade as product behavior.

### API client (typed end-to-end)

```python
class OrdersClient(BaseClient):
    async def create_order(self, payload: CreateOrderRequest) -> OrderResponse:
        resp = await self._http.post("/store/orders", json=payload.model_dump())
        return OrderResponse.model_validate(resp.json())
```

Rule: handlers accept/return model instances; `model_dump()` happens exactly once at the transport edge; response validation errors surface as failures, not silent `dict`s.

### Test data isolation

Fixture-generated identities carry the run namespace: `qa-{run_id}-{n}@example.invalid`, codes/notes suffixed with `run_id`. Seeds live in `shared/testdata/` hooks invoked by `make target-app-seed`; cleanup is best-effort via APIs/container rebuild and never by direct DB writes (Architecture §6 scope).

## Patch Rules During Self-Debug

Full taxonomy in PRD §4.7; implementation-facing summary:

- Allowed edit surface: whitelisted `automation/**` paths plus owned shared utils — selectors, waits, fixtures, imports, serialization, types.
- Frozen forever: assertions' expected values & semantics, marker tags, collection config, anything outside `automation/**`.
- Every cycle passes the verification battery (ruff/pyright/POM/markers checks) before re-run; failed static gates burn budget and revert.
- Assertion-density drop between attempts (`delta_assertions < 0`) is an automatic escalation signal.

## Anti-Patterns

| Anti-pattern | Effect | Required practice | Basis |
| --- | --- | --- | --- |
| Selector literal inside a test function | Boundary erosion; duplicate maintenance | Locators only in page/component objects | Architecture §5 checker |
| Assertions inside page objects | Objects become route-specific; reuse dies | Return values; test asserts | same |
| Raw `dict` payloads in API clients | Untyped drift; hallucinated fields survive | Pydantic models both directions | `check_api_models.py` |
| `wait_for_timeout(...)` to fix flake | Masks timing bugs; inflates suite time | Wait on expected state (`expect(locator).to_be_visible()` etc.) | review adoption |
| Broad `try/except Exception: pass` in tests/shared | Swallows real failures; enables fake greens | Let exceptions fail; classify via failure classes | PRD §4.7 ban list |
| Tests importing/reading `iterations/**` at runtime | Couples long-lived assets to mutable iteration data; breaks layering | Read own pytest markers | dependency table |
| Hand-editing derived views (`.md`/`.xmind`/`.xlsx`) or `exports/` | Diverges from source-of-truth YAML | Regenerate via `export_*` scripts | ADR-007 |
| Adding dependencies ad hoc | Undermines lockfile/reproducibility | Declare in pyproject groups per purpose (core/dev/mobile/perf) | pyproject layout |

## Skill Authoring Conventions

Every `SKILL.md` follows one shape so cross-model behavior stays comparable (merged from the former Implementation Guide §3):

```markdown
---
name: test-design
version: 1.0.0
description: >
  Use for the full test-design phase: raw requirement dump -> clarified
  requirement -> test points -> functional cases.yaml -> xmind export.
  Owns confirmation points 1-3 in that order.
---
## Inputs / Outputs
(inputs; outputs in order, each gated by validate_schema.py;
 approvals written to iterations/<id>/iteration.yaml)
## Stop-and-confirm points
(explicit user acceptance between stages; every acceptance appends
 {stage, action, actor=user, timestamp, artifact_sha256} to approvals[])
## Rules
- Never invent content absent from 00-raw/ or user answers.
- Populate traceability links while generating, never deferred.
- Input-hash gating: unchanged inputs => no-op unless --force.
- On schema validation failure: fix -> re-validate; budget 3, then surface.
```

Generation-skill rules block (web variant; API analog adds pydantic-model pairing): one page object per route under `pages/<module>/`, creating the module dir when new · tests import page objects only — selector literals fail `check_pom_boundary.py`, assertions live in tests only · markers `module/case_id/iteration` on every test with path consistency enforced by `check_test_markers.py`; run selection is by directory · reuse-before-create across `pages/` + `components/` · traceability upsert of nodeids immediately. Frontmatter carries `version:` for future upstream diffing (ADR-003). The self-debug loop's behavioral rules live in PRD §4.7 and ADR-004; its SKILL.md is a Roadmap Phase 5 deliverable conforming to this template.
