# ADR-002: Medusa as the first end-to-end target application

- Date: confirmed during design phase (exact session date not recorded); consolidated on 2026-08-27
- Status: Accepted
- Related: Implementation Guide §Target App Harness (expanded scope), Roadmap Phase 5 prerequisite + Phase 9

## Background

The framework needs one real application to exercise web UI + API paths end to end. Criteria: open source, actively maintained, REST APIs documented, has login/cart/checkout flows, small enough for a first pass.

## Decision & Rationale

Use **Medusa** (open-source headless commerce; Node/TS backend, Next.js storefront candidate) pinned to an exact version. Everything outside the walkthrough stays app-agnostic.

Evidence-based corrections adopted at consolidation (from review): Medusa's storefront ships as a separate starter app or via `create-medusa-app`, admin auth (JWT) differs from store auth (publishable API key), built-in UI lacks the bespoke `data-testid`s used in v1.0 examples, and docker-compose brings Postgres (+Redis). Therefore **version pinning and a written `knowledge/target-app-notes/medusa.md` are prerequisites** that moved ahead of web-automation phases instead of a Phase-8 afterthought (Roadmap reordering).

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| Self-built demo app | Zero credibility as a regression target; maintenance burden | IG v1.0 discussion |
| Larger OSS apps | First pass would take weeks; violates scoping criterion | IG v1.0 discussion |

## Impact

Target-app harness scripts (up/seed/reset/healthcheck/down), locked compose file, and seeded commerce data (region/currency, product+inventory, shipping option, manual payment provider, discount code) become explicit deliverables (Implementation Guide §Harness; Roadmap tasks).
