# plugins/

Fetch + normalize layer between external sources and the skill layer
(ARCHITECTURE §1). A plugin resolves a source ref into a normalized
**source payload envelope**, persisted to disk by `scripts/run_plugin.py`
*before* schema validation — never in-memory handoff, never case-design
logic, never LLM calls inside a plugin (ADR-006).

- `_interface/contract.md` — envelope rules (authored in Roadmap 2.1)
- `_interface/schemas/` — `*_source_payload.schema.json` (DATA_MODEL §10)
- `requirement-sources/` / `api-sources/` — connector placeholders (post-v1)

Registration: `registry.yaml` is the only name→plugin lookup.
