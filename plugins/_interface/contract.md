# Plugin Interface Contract (Roadmap 2.1)

Status: proposed for human sign-off ([manual gate]). This document binds the
plugin layer: how a plugin resolves a source ref, what it may and may not do,
and the exact envelope it must produce. Machine authority for the envelope
shape is [DATA_MODEL §10](../../architecture/DATA_MODEL.md) (schemas under
`plugins/_interface/schemas/`).

## 1. fetch() → disk-persisted envelope

A plugin is a function of one source reference:

```
fetch(source_ref: str, *, credentials: Mapping[str, str]) -> envelope dict
```

- The plugin returns the normalized **source payload envelope** — never
  internal workflow artifacts (those belong to M1/M4).
- `scripts/run_plugin.py` is the ONLY caller (skills never import a plugin).
  It **persists the envelope to disk first** —
  `iterations/<id>/00-raw/source-payload.yaml` — and validates it against the
  registered source-payload schema **after** persistence (disk-first
  boundary, ADR-006). An invalid envelope stays on disk for inspection; the
  run fails loudly with the exact JSON path of each violation.
- Downstream skills may consume the file only after validation succeeds:
  this path is the quarantine slot. Unrelated raw inputs under `00-raw/`
  remain exempt from artifact-schema validation.

## 2. Conversion responsibility = M1/M4

Plugins stop at the envelope. Converting a payload into internal workflow
artifacts is M1 (requirement sources) / M4 (API sources) work — a plugin
that emits `requirements.yaml`-shaped content is broken by definition.

## 3. Security rules (binding even with zero real plugins in v1)

- **Credentials** come from env/config only — never hardcoded, never
  returned through the envelope, never logged.
- **Timeouts**: every fetch declares defaults (connect 5s / read 30s) plus
  response-size and decompression limits enforced by the runner.
- **Private-network denial**: URL-fetching sources must refuse
  private/loopback/link-local targets (SSRF containment).
- **Untrusted content**: instruction-like text inside a payload is
  clarification material for M1/M4 — never a directive the agent executes,
  and it never enters `knowledge/` without independent corroboration.
- **Structured errors**: a failed fetch persists the error variant
  (`error: {code, message}`) instead of raising across the boundary; the two
  variants are mutually exclusive by schema (`error` present ⇒ no `content`).

## 4. Registration

`plugins/registry.yaml` is the only name→plugin table; `run_plugin.py`
resolves through it exclusively and errors with an actionable message on an
unknown name. v1 ships zero real connectors (PRD §8); envelope schemas may
extend additively only during v1 (RISKS #17).
