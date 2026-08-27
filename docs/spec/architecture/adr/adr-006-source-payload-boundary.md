# ADR-006: Plugins emit source-payload envelopes, not internal workflow artifacts

- Date: 2026-08-27
- Status: Accepted
- Related: Architecture §1/§3, DATA_MODEL §10, PRD §3 M14, Roadmap Phase 2

## Background

v1.0's plugin contract said `fetch(source_ref) -> dict` validated against internal schemas (`requirements.schema.json` / `api_spec.schema.json`). Contradictions follow: PRD requires every layer-crossing payload be persisted YAML-first (a returned dict isn't), and external connectors cannot know workflow-owned fields (`iteration_id`, statuses) they'd be forced to fabricate to pass validation. Direction prose ("plugins → skills") also read as a dependency allowance that the dependency table forbade.

## Decision & Rationale

Three clarifications:

1. **Disk-first boundary**: `scripts/run_plugin.py` writes the plugin output to `iterations/<id>/00-raw/source-payload.yaml` and validates it there — satisfying the persistence rule for plugin boundaries too.
2. **Envelope schemas**: plugins validate against dedicated `*_source_payload.schema.json` envelopes (DATA_MODEL §10). Conversion from envelope to internal artifacts is M1/M4 work. Skills never see raw platform payloads; plugins never fake workflow fields.
3. **Direction statement fixed**: data flows plugin→skill; dependency runs skill→script→plugin via `run_plugin.py`. Both now stated separately (Architecture §1).

Contract additions bundled here so the first real integration doesn't invalidate the contract: credentials via env/config only, private-network fetch denial, default timeouts, structured error envelope.

## Considered Alternatives

| Alternative | Why not chosen | Basis |
| --- | --- | --- |
| Reuse internal schemas at the plugin boundary (v1.0) | Forces fabrication of unknown fields; couples plugins to pipeline internals | GPT P1-1 / Grok analysis |
| Let skills import plugin modules directly | Breaks layering; makes skill portability depend on repo layout | v1.0 design intent, retained |

## Impact

Two more schema files + registry entries; M1/M4 gain an explicit conversion step; Phase 2 roadmap tasks extend to envelope persistence tests.
