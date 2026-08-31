# Data Model

Version: 1.7 · Schema contracts updated after the Claude, Grok, GPT, and post-v1.5 review adoptions.

Authoritative machine contracts for every YAML artifact crossing a layer boundary. Architecture §1's validation layer enforces these; PRD §2–§5 defines their business meaning. Field-level rules not expressible in JSON Schema (cross-file references, ID uniqueness, staged coverage) live in the **semantic checks** listed in §12 and are enforced by scripts, not prose.

Conventions for all persisted artifacts:

- Top-level `schema_version: "1.0"` is mandatory everywhere.
- Status enums are lowercase snake_case fileside (GLOSSARY).
- Unless stated otherwise, objects set `"additionalProperties": false` — unknown fields fail validation. This is deliberate drift protection.
- IDs follow GLOSSARY formats. Uniqueness scopes differ per artifact; see each entity's "ID" line.
- **Dialect honesty (Draft-07)**: `default` keywords are annotations, not value injection — producing tools (scaffolder/generators) materialize defaults; validators never assume them. Every conditional (`if`) carries an explicit `required` so absent properties cannot satisfy the condition vacuously. Validators run with a `FormatChecker` enabled so `format: date-time` rejects malformed strings.
- **Evolution policy**: each artifact pins its `schema_version` (`const "1.0"` for the current YAML contracts). Additive extensions (new files, new registered artifacts) need no migration; changing or removing an existing definition normally requires a new schema version plus a registry entry and a migration note. ADR-015 records the explicit pre-release clean-break exception for the tightened functional/API test-design contracts; execution manifests are a new JSON contract at `1.1` under ADR-014.
- **`generated_from` depth**: the embedded schemas record the single *direct* parent (`artifact`, `sha256`). Generators producing from multiple inputs (requirements + user answers + spec) additionally emit an optional `inputs: [{artifact, sha256, role}, ...]` field inside `generated_from`; staleness semantics compare every listed hash (single form reads as a one-element list). Producer attribution (skill version, model/session) lives in `events[].triggered_by` metadata and skill frontmatter versions, deliberately not duplicated into every artifact. The committed `.schema.json` files under the registry are the executable authority for this extension.

Schema placement follows production ownership: `requirements/test_points/functional_cases` schemas under `.agents/skills/functional-test-design/schemas/`; `api_spec` + `api_cases` under `.agents/skills/api-test-design/schemas/`; `exemptions`, `iteration`, `traceability`, `run_summary` under `scripts/schemas/`; `*_source_payload` under `plugins/_interface/schemas/`. Filename↔artifact binding is an explicit registry table (`scripts/schema_registry.yaml`) — never inferred from filename similarity.

## 1. Entity relationships

| Entity | Meaning | Relationship / cardinality | Basis |
| --- | --- | --- | --- |
| IterationState | Aggregate lifecycle record of one iteration | 1 → 0..1 of each workflow artifact in its directory; 1 → N runs | PRD §2.1, §5 |
| Requirement | Clarified unit of demand (R####) | UI-led: 1 → 1..N TestPoint, unless an accepted exemption; API-led: 1 → 1..N APICase | PRD §4.1–4.4 |
| TestPoint | Testable angle on requirement(s) (T####) | 1 → 0..N FunctionalCase | PRD §4.2–4.3 |
| FunctionalCase | Executable manual scenario (C####) | 0..N rows' source in TraceabilityRecord; → AutomationTest(s) | PRD §4.3 |
| NormalizedSpec | Module-tagged endpoint catalog | 1 endpoint → 2..N APICase (happy + negative/edge, unless out-of-scope) | PRD §4.4 |
| APICase | Single API verification (A####) | 1..N `requirement_ids[]` → AutomationTest(s) | PRD §4.4 |
| Exemption | Reasoned exception to a requirement's testability/automation path | 0..1 per requirement; `not_testable` removes R from coverage, `manual_only` stops at the case tier | PRD §4.2, DATA_MODEL §2.1 |
| AutomationTest | Long-lived pytest node under `automation/` | referenced by traceability nodeids | PRD §4.5–4.6 |
| TraceabilityRecord | Sparse link row per requirement chain | N sparse rows; coverage computed, never hand-written | PRD §3 M10, ADR-005 |
| RunResult | One self-debug invocation outcome | N per iteration | PRD §4.7 |

## 2. `requirements.yaml`

Schema: `.agents/skills/functional-test-design/schemas/requirements.schema.json`. ID: GLOSSARY `requirement_id`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "requirements"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["draft", "clarifying", "clarified", "accepted"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "requirements": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["requirement_id", "title", "description"],
        "properties": {
          "requirement_id": {"type": "string", "pattern": "^R[0-9]{4}$"},
          "title": {"type": "string", "minLength": 1},
          "description": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "enum": [1, 2, 3], "default": 2},
          "source": {"type": "string"}
        }
      }
    },
    "ambiguities": {
      "type": "array",
      "items": {"$ref": "#/definitions/ambiguity"}
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"const": "accepted"}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    },
    {
      "if": {"properties": {"status": {"enum": ["clarified", "accepted"]}}, "required": ["status"]},
      "then": {"properties": {"ambiguities": {"items": {"properties": {"resolved": {"const": true}}}}}}
    },
    {
      "if": {"properties": {"status": {"const": "clarifying"}}, "required": ["status"]},
      "then": {"properties": {"ambiguities": {"minItems": 1}}}
    }
  ],
  "definitions": {
    "generated_from": {
      "type": "object",
      "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {
        "artifact": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
      }
    },
    "ambiguity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["question", "resolved"],
      "properties": {
        "question": {"type": "string", "minLength": 1},
        "asked_at": {"type": "string"},
        "resolved": {"type": "boolean"},
        "resolution": {"type": "string"}
      },
      "allOf": [
        {"if": {"properties": {"resolved": {"const": true}}},
         "then": {"required": ["resolution"], "properties": {"resolution": {"minLength": 1}}}}
      ]
    }
  }
}
```

Resolved ambiguity entries are **audit evidence and are retained**, not deleted; PRD §4.1's earlier "no ambiguity entries remain" wording is superseded by this document (kept-with-resolution). The two status conditionals together enforce: clarified/accepted ⇒ no unresolved entries; clarifying ⇒ at least one question outstanding (prevents skipping the asking step). `priority` is proposed by M1 from clarification and confirmed by the user at accept; an omitted value is treated as 2 by every semantic consumer (PRD §4.2's priority-1 rule reads this field).

## 2.1 `exemptions.yaml`

Schema: `scripts/schemas/exemptions.schema.json`. Exemptions are deliberately separate from accepted requirements: M1's accepted `requirements.yaml` is immutable, while M2 records a reasoned exception when a requirement cannot be tested or is intentionally manual-only.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "exemptions"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["draft", "review", "accepted"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "exemptions": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["requirement_id", "kind", "reason"],
        "properties": {
          "requirement_id": {"type": "string", "pattern": "^R[0-9]{4}$"},
          "kind": {"enum": ["not_testable", "manual_only"]},
          "reason": {"type": "string", "minLength": 1}
        }
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"const": "accepted"}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    }
  ],
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {
        "artifact": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
      }
    }
  }
}
```

Semantic checks: each requirement has at most one exemption; `not_testable` removes it from R→T/R→A demand and `manual_only` permits the case tier but removes it from the automation tier. An accepted UI iteration requires every requirement to have a test point or exemption. An accepted API iteration requires every non-exempt requirement to appear in at least one API case's `requirement_ids[]`; on the API branch exemptions are produced during M4's requirements-mapping sub-stage (there is no M2), so this file's producer is branch-dependent by design.

## 3. `iteration.yaml`

Schema: `scripts/schemas/iteration.schema.json`. This is the persistence home for PRD §5's global state machine — before v1.1 it had no backing file, which broke the auditability NFR.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "state", "branches", "artifacts"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "state": {"enum": [
      "created", "blocked",
      "requirements_clarifying", "requirements_accepted", "requirements_mapped",
      "test_points_review", "test_points_accepted",
      "functional_cases_generating", "functional_cases_exported",
      "spec_normalizing", "spec_valid",
      "api_cases_generating", "api_cases_exported",
      "web_automation_generating", "web_automation_generated",
      "api_automation_generating", "api_automation_generated",
      "env_pending", "env_configured",
      "executing", "execution_passed", "execution_budget_exceeded", "escalated",
      "acceptance_pending", "accepted", "merged"
    ]},
    "blocked_reason": {"type": ["string", "null"]},
    "branches": {
      "type": "object", "additionalProperties": false,
      "required": ["ui", "api"],
      "properties": {"ui": {"type": "boolean"}, "api": {"type": "boolean"}},
      "oneOf": [
        {"properties": {"ui": {"const": true}, "api": {"const": false}}},
        {"properties": {"ui": {"const": false}, "api": {"const": true}}}
      ]
    },
    "delegation": {
      "$ref": "#/definitions/delegation"
    },
    "artifacts": {
      "type": "object", "additionalProperties": false,
      "required": ["requirements", "test_points", "functional_cases",
                    "api_spec", "api_cases", "web_automation", "api_automation", "execution"],
      "properties": {
        "requirements":    {"$ref": "#/definitions/artifact_status"},
        "exemptions":      {"$ref": "#/definitions/artifact_status"},
        "test_points":     {"$ref": "#/definitions/artifact_status"},
        "functional_cases":{"$ref": "#/definitions/artifact_status"},
        "api_spec":        {"$ref": "#/definitions/artifact_status"},
        "api_cases":       {"$ref": "#/definitions/artifact_status"},
        "web_automation":  {"$ref": "#/definitions/artifact_status"},
        "api_automation":  {"$ref": "#/definitions/artifact_status"},
        "execution":       {"$ref": "#/definitions/artifact_status"}
      }
    },
    "approvals": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["stage", "action", "actor", "timestamp", "artifact_sha256"],
        "properties": {
          "stage": {"enum": ["requirements", "exemptions", "test_points", "environment", "skill_change", "acceptance"]},
          "action": {"enum": ["accepted", "rejected", "provided", "approved", "delegated"]},
          "actor": {"enum": ["user", "agent"]},
          "timestamp": {"type": "string", "format": "date-time"},
          "artifact_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "note": {"type": "string"},
          "delegation_id": {"type": "string", "pattern": "^delegation-[a-z0-9-]+$"}
        },
        "allOf": [{
          "if": {"properties": {"action": {"const": "delegated"}}, "required": ["action"]},
          "then": {
            "properties": {"actor": {"const": "agent"}, "note": {"minLength": 1}},
            "required": ["note", "delegation_id"]
          },
          "else": {
            "properties": {"actor": {"const": "user"}},
            "not": {"required": ["delegation_id"]}
          }
        }]
      }
    },
    "events": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["from_state", "to_state", "timestamp", "triggered_by"],
        "properties": {
          "from_state": {"type": "string"},
          "to_state": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"},
          "triggered_by": {"enum": ["agent", "script", "user"]},
          "delegation_id": {"type": "string", "pattern": "^delegation-[a-z0-9-]+$"}
        }
      }
    },
    "source_manifest": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["path", "sha256", "captured_at"],
        "properties": {
          "path": {"type": "string"},
          "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "captured_at": {"type": "string", "format": "date-time"},
          "redacted": {"type": "boolean", "default": false}
        }
      }
    },
    "updated_at": {"type": "string", "format": "date-time"}
  },
  "definitions": {
    "delegation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "granted_by", "basis", "basis_sha256", "scope", "granted_at", "expires_at"],
      "properties": {
        "id": {"type": "string", "pattern": "^delegation-[a-z0-9-]+$"},
        "granted_by": {"const": "user"},
        "basis": {"type": "string", "minLength": 1},
        "basis_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "scope": {"type": "array", "minItems": 1, "uniqueItems": true,
                  "items": {"enum": ["exemptions", "test_points", "environment", "acceptance", "skill_change", "lifecycle_reopen"]}},
        "granted_at": {"type": "string", "format": "date-time"},
        "expires_at": {"type": "string", "format": "date-time"}
      }
    },
    "artifact_status": {
      "type": "object", "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {"enum": ["not_started", "draft", "clarifying", "clarified", "accepted",
                             "review", "validating", "valid", "exported", "generating",
                             "linting", "generated", "spec_draft", "spec_valid",
                             "cases_draft", "cases_valid", "running", "passed",
                             "budget_exceeded", "escalated", "stale"]},
        "input_sha256": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"}
      }
    }
  }
}
```

Semantic check (scripts, not schema): transitions follow PRD §5 routes (`requirements_mapped` applies to the API branch only); v1 requires exactly one of `branches.ui` and `branches.api` to be true, while the both-true Hybrid route is reserved for post-v1; `blocked` clears only via user action; stale propagation rewrites artifact statuses to `stale`. Writer convergence: `state` and `events[]` are written exclusively by `scripts/record_event.py` (called by skills after each legal transition); regular `approvals[]` entries are written exclusively by `scripts/record_approval.py`; the structured `delegation` grant and its one-time legacy binding are written exclusively by `scripts/record_delegation.py`; hand edits to either namespace are validation errors. Explicit user decisions use `actor: user`; M1 `requirements` acceptance is always user-only and is not a delegation scope. A delegated decision for a later repository stage is valid only with `action: delegated`, `actor: agent`, a matching `delegation_id`, a non-empty note, and a delegation object whose issuer is `user`, basis hash, scope, and validity window all verify. An agent reopen additionally requires the `lifecycle_reopen` scope and stores the same delegation id on the event; delegation ids on unrelated events are invalid. Both decision types bind the current artifact digest and cannot replace environment mechanical checks, real execution evidence, notification delivery, non-author review, or a real merge SHA. `exemptions` in `artifacts` is an optional aggregate mirror — the authoritative exemption state remains `exemptions.yaml` itself.

## 4. `test_points.yaml`

Schema: `.agents/skills/functional-test-design/schemas/test_points.schema.json`. ID: GLOSSARY `test_point_id`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "test_points"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["draft", "review", "accepted"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "test_points": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["test_point_id", "requirement_ids", "description", "type"],
        "properties": {
          "test_point_id": {"type": "string", "pattern": "^T[0-9]{4}$"},
          "requirement_ids": {"type": "array", "minItems": 1,
            "items": {"type": "string", "pattern": "^R[0-9]{4}$"}},
          "description": {"type": "string", "minLength": 1},
          "type": {"enum": ["happy", "negative", "boundary"]},
          "priority": {"type": "integer", "enum": [1, 2, 3]}
        }
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"const": "accepted"}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    }
  ],
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {"artifact": {"type": "string", "minLength": 1},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

## 5. `functional-cases.yaml`

Schema: `.agents/skills/functional-test-design/schemas/functional_cases.schema.json` (test-design clean-break rules: ADR-015). Now complete (v1.0 deferred to "as previously specified", which pointed nowhere — fixed).

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "cases"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["draft", "validating", "valid", "exported"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "cases": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["case_id", "title", "priority", "precondition", "steps", "tags", "test_point_ids"],
        "properties": {
          "case_id": {"type": "string", "pattern": "^C[0-9]{4}$"},
          "title": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "enum": [1, 2, 3]},
          "precondition": {"type": "string", "minLength": 1},
          "steps": {
            "type": "array", "minItems": 1,
            "items": {
              "type": "object", "additionalProperties": false,
              "required": ["action", "expected", "expected_kind"],
              "properties": {
                "action": {"type": "string", "minLength": 1},
                "expected": {"type": "string", "minLength": 1},
                "expected_kind": {"enum": ["ui_state", "copy", "derived_value"]},
                "derived_from": {"$ref": "#/definitions/derived_from"}
              },
              "allOf": [
                {
                  "if": {"properties": {"expected_kind": {"const": "derived_value"}}, "required": ["expected_kind"]},
                  "then": {"required": ["derived_from"]}
                }
              ]
            }
          },
          "tags": {
            "type": "array", "items": {"type": "string"}, "minItems": 1,
            "contains": {"type": "string", "pattern": "^module:[a-z][a-z0-9_]*$"}
          },
          "test_point_ids": {"type": "array", "minItems": 1,
            "items": {"type": "string", "pattern": "^T[0-9]{4}$"}}
        }
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"enum": ["valid", "exported"]}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    }
  ],
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {"artifact": {"type": "string", "minLength": 1},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    },
    "derived_from": {
      "type": "object", "additionalProperties": false,
      "required": ["seed", "rule"],
      "properties": {
        "seed": {"type": "string", "minLength": 1},
        "rule": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

The `module:` tag drives `automation/web/{pages,tests}/<module>/` placement downstream (PRD §4.5) — exactly one required. Draft-07 has no usable `maxContains`, so `contains` enforces ≥1 at the schema layer and **tag uniqueness is enforced semantically** by `check_functional_expectations.py` (§12); a second `module:` tag fails validation even though raw JSON Schema would accept it. `derived_from.seed` values must resolve against the target app's seed registry (`shared/testdata/seed-registry.yaml`, produced with the harness per Roadmap 5.0.2): the check is advisory while no registry exists for the target app (early M3 dry-runs) and a hard gate from M6 generation onward, so hallucinated seed names are rejected before any code consumes them.

Export contract for `.xmind`: the root tree is `iteration → module → requirement (R####) → test point (T####) → functional case (C####) → step`. IDs and titles are preserved at each node; a case linked to multiple requirements/test points appears under each applicable source path without changing the source IDs. Golden fixtures assert this hierarchy, not only ZIP validity.

## 6. `api/spec.normalized.yaml`

Schema: `.agents/skills/api-test-design/schemas/api_spec.schema.json`. **New in v1.1** — v1.0 referenced this schema in three places without defining it anywhere.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "service_name", "endpoints"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["spec_draft", "spec_valid"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "service_name": {"type": "string", "minLength": 1},
    "base_path": {"type": "string"},
    "auth_model": {"type": "string"},
    "components": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "schemas": {
          "type": "object", "minProperties": 1,
          "additionalProperties": {"$ref": "#/definitions/schema_fragment"}
        }
      }
    },
    "normalization_warnings": {
      "type": "array",
      "items": {"type": "object", "additionalProperties": false,
        "required": ["code", "detail"],
        "properties": {"code": {"type": "string"}, "detail": {"type": "string"}, "location": {"type": "string"}}}
    },
    "source_refs": {
      "type": "array", "minItems": 1,
      "items": {"type": "object", "additionalProperties": false,
        "required": ["kind", "location"],
        "properties": {"kind": {"enum": ["openapi", "har", "postman", "source_code", "dev_docs", "plugin"]},
                        "location": {"type": "string"}}}
    },
    "endpoints": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["operation_id", "path", "method", "module", "parameters", "responses"],
        "properties": {
          "operation_id": {"type": "string", "minLength": 1},
          "path": {"type": "string", "pattern": "^/"},
          "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
          "summary": {"type": "string"},
          "module": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
          "requirement_ids": {"type": "array", "minItems": 1,
            "items": {"type": "string", "pattern": "^R[0-9]{4}$"}},
          "authentication": {"type": "string"},
          "parameters": {"type": "array", "items": {"$ref": "#/definitions/param"}},
          "request_body": {
            "type": "object", "additionalProperties": false,
            "required": ["content_type", "schema"],
            "properties": {"content_type": {"type": "string"}, "schema": {"$ref": "#/definitions/schema_fragment"}, "example": {}}
          },
          "responses": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": false,
            "required": ["status_code"],
            "properties": {"status_code": {"type": "integer"}, "description": {"type": "string"}, "body_schema": {"$ref": "#/definitions/schema_fragment"}}}},
          "out_of_scope": {"type": "boolean", "default": false},
          "out_of_scope_reason": {"type": "string"}
        },
        "allOf": [
          {"if": {"properties": {"out_of_scope": {"const": true}}, "required": ["out_of_scope"]},
           "then": {"required": ["out_of_scope_reason"],
                     "properties": {"out_of_scope_reason": {"minLength": 1}}}}
        ]
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"const": "spec_valid"}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    }
  ],
  "definitions": {
    "param": {
      "type": "object", "additionalProperties": false,
      "required": ["name", "in", "required", "schema"],
      "properties": {"name": {"type": "string", "minLength": 1},
                      "in": {"enum": ["path", "query", "header", "cookie"]},
                      "required": {"type": "boolean"},
                      "schema": {"$ref": "#/definitions/schema_fragment"},
                      "example": {}}
    },
    "schema_fragment": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "$ref": {"type": "string", "pattern": "^#/components/schemas/[A-Za-z0-9_.-]+$"},
        "type": {"enum": ["object", "array", "string", "integer", "number", "boolean"]},
        "format": {"type": "string"},
        "enum": {"type": "array", "minItems": 1},
        "required": {"type": "array", "items": {"type": "string"}},
        "properties": {"type": "object", "additionalProperties": {"$ref": "#/definitions/schema_fragment"}},
        "items": {"$ref": "#/definitions/schema_fragment"},
        "allOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}},
        "oneOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}},
        "anyOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}}
      },
      "oneOf": [{"required": ["type"]}, {"required": ["$ref"]},
                 {"anyOf": [{"required": ["allOf"]}, {"required": ["oneOf"]}, {"required": ["anyOf"]}]}]
    },
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {"artifact": {"type": "string", "minLength": 1},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

Semantic check: when an OpenAPI source uses `components.schemas`, the normalized spec must retain every referenced component schema (including nested `$ref` links) and reject dangling references. Inline parameter, request-body, and response schemas remain valid when the source has no component references; the normalizer may inline only when it can preserve equivalent type information.

**Reference-resolution rules**: the normalizer enforces a **maximum `$ref` resolution depth of 5** (flattening depth, not document depth — mutually recursive components are preserved as `$ref` links, never inlined into a cycle). Beyond the limit, a branch degrades to `type: object` and records an entry in the top-level `normalization_warnings[]` (`code`, `detail`, `location`) instead of failing or silently truncating. Combinators (`allOf`/`oneOf`/`anyOf`) are preserved verbatim as legal `schema_fragment` properties — dropping or flattening them into pseudo-objects is prohibited because their semantics drive negative-case generation in M5. `check_api_models.py` treats a warning-degraded branch as "structure not sufficient", so M7 escalates instead of inventing typed models for it.

**Test projection, not lossless replacement**: `spec.normalized.yaml` is a *derived view* of the original interface description. The untouched source OpenAPI document (or HAR/postman export) is committed under the iteration's `00-raw/` with its sha256 in `iteration.yaml.source_manifest[]`, and the matching `source_refs[].location` points there. Structures this projection cannot carry (servers, security schemes/scopes, media-type variants beyond `content_type`, headers on responses, callbacks/webhooks) remain authoritative in the source file; M7 generates typed request/response models only for operations whose structures survived normalization intact, and escalates to the user instead of inventing types where they did not. Unrecoverable unknowns are recorded as explicit notes on the endpoint (`authentication` prose, missing examples), never silently filled.

## 7. `api/cases.yaml`

Schema: `.agents/skills/api-test-design/schemas/api_cases.schema.json` (test-design clean-break rules: ADR-015). Fixes vs v1.0: `iteration_id` declared in properties (was required-but-undefined), lifecycle status names align with the global state machine, `module` is mandatory (it determines generation paths), every case cites its `operation_id` and `requirement_ids[]`, and requests preserve replayable variable sources.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "cases"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "status": {"enum": ["cases_draft", "cases_valid", "exported"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "cases": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["api_case_id", "requirement_ids", "operation_id", "endpoint", "method", "title",
                      "case_type", "module", "request", "expected_response"],
        "properties": {
          "api_case_id": {"type": "string", "pattern": "^A[0-9]{4}$"},
          "requirement_ids": {"type": "array", "minItems": 1,
            "items": {"type": "string", "pattern": "^R[0-9]{4}$"}},
          "operation_id": {"type": "string", "minLength": 1},
          "endpoint": {"type": "string", "pattern": "^/"},
          "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
          "title": {"type": "string", "minLength": 1},
          "case_type": {"enum": ["happy_path", "negative", "edge"]},
          "side_effect": {"enum": ["none", "creates", "updates", "deletes"], "default": "none"},
          "module": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
          "request": {
            "type": "object", "additionalProperties": false,
            "properties": {
              "path_params": {"type": "object"},
              "query": {"type": "object"},
              "headers": {"type": "object"},
              "body": {},
              "variables": {
                "type": "array",
                "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["name", "source", "expression"],
                  "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "source": {"enum": ["seed", "path", "prev_response"]},
                    "expression": {"type": "string", "minLength": 1}
                  }
                }
              }
            }
          },
          "expected_response": {
            "type": "object", "additionalProperties": false,
            "required": ["status_code"],
            "properties": {"status_code": {"type": "integer"},
                            "body_schema": {"$ref": "#/definitions/schema_fragment"},
                            "body_includes": {"type": "object"},
                            "body_assertions": {"type": "array", "minItems": 1},
                            "derived_oracles": {"type": "array"}}
          }
        }
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"enum": ["cases_valid", "exported"]}}, "required": ["status"]},
      "then": {"required": ["generated_from"]}
    }
  ],
  "definitions": {
    "schema_fragment": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "$ref": {"type": "string", "pattern": "^#/components/schemas/[A-Za-z0-9_.-]+$"},
        "type": {"enum": ["object", "array", "string", "integer", "number", "boolean"]},
        "format": {"type": "string"},
        "enum": {"type": "array", "minItems": 1},
        "required": {"type": "array", "items": {"type": "string"}},
        "properties": {"type": "object", "additionalProperties": {"$ref": "#/definitions/schema_fragment"}},
        "items": {"$ref": "#/definitions/schema_fragment"},
        "allOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}},
        "oneOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}},
        "anyOf": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/schema_fragment"}}
      },
      "oneOf": [{"required": ["type"]}, {"required": ["$ref"]},
                 {"anyOf": [{"required": ["allOf"]}, {"required": ["oneOf"]}, {"required": ["anyOf"]}]}]
    },
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "required": ["artifact", "sha256"],
      "properties": {"artifact": {"type": "string", "minLength": 1},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

Export contract for `.xlsx`: the first row contains `api_case_id`, `module`, `operation_id`, `method`, `endpoint`, `case_type`, `title`, `request.path_params`, `request.query`, `request.headers`, `request.body`, `request.variables`, `expected_response.status_code`, `expected_response.body_schema`, and `expected_response.body_includes`. Export tests assert the exact header set, populated required cells, and round-trip preservation of the source values.

## 8. `traceability.yaml`

Schema: `scripts/schemas/traceability.schema.json`. Redesign rationale (ADR-005): v1.0 required `test_point_id` on every row yet also offered a `coverage_status` of `requirement_only` — unrepresentable states. v1.1 makes rows **sparse** and removes the hand-written status entirely; coverage depth is *derived* by `check_coverage.py`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "links"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "links": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["requirement_id"],
        "properties": {
          "requirement_id": {"type": "string", "pattern": "^R[0-9]{4}$"},
          "test_point_id": {"type": "string", "pattern": "^T[0-9]{4}$"},
          "functional_case_id": {"type": "string", "pattern": "^C[0-9]{4}$"},
          "api_case_id": {"type": "string", "pattern": "^A[0-9]{4}$"},
          "automation_test_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": "^automation/[^\\x00\\\\\\r\\n]+::[^\\x00\\\\\\r\\n]+$"}
          },
          "retires_nodeids": {
            "type": "array",
            "items": {"type": "string", "pattern": "^automation/[^\\x00\\\\\\r\\n]+::[^\\x00\\\\\\r\\n]+$"}
          }
        },
        "oneOf": [
          {"required": ["functional_case_id"], "not": {"required": ["api_case_id"]}},
          {"required": ["api_case_id"], "not": {"required": ["functional_case_id"]}},
          {"not": {"anyOf": [{"required": ["functional_case_id"]}, {"required": ["api_case_id"]}]}}
        ]
      }
    }
  }
}
```

JSON Schema validates *shape*; `check_coverage.py` enforces semantics per branch and tier (§12). UI updates are idempotent upserts keyed on `(iteration_id, requirement_id, test_point_id?, functional_case_id?)`; API updates are keyed on `(iteration_id, requirement_id, api_case_id)`. Retired nodeids remain auditable in `retires_nodeids[]` and are excluded from active automation coverage. Concurrent-looking repeated writes converge to one row, no duplicates.

## 9. `run-summary.yaml`

Schema: `scripts/schemas/run_summary.schema.json`. Adds the `run_id` promised by PRD §2.1, timing, scope, and the failure-class taxonomy that powers M9's escalation logic. Since v1.4 each execution persists to its own directory `iterations/<id>/runs/<run_id>/` (`run-summary.yaml` + captured evidence — ADR-010); no later run may overwrite an earlier one, and any copies under global `reports/` are display-only scratch, never the fact source. `failed` exists for single-shot executions without a debug loop — CI's `record-ci` mode (self_debug_helper.py reading junit/allure) writes `scope: full` with one attempt documenting the execution outcome; trace/log artifacts under the run directory are gitignored per ADR-012.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "run_id", "status",
                "retry_budget", "modules", "attempts"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "run_id": {"type": "string", "pattern": "^run-[0-9]{8}T[0-9]{6}Z(-[a-z0-9]{4})?$"},
    "started_at": {"type": "string", "format": "date-time"},
    "finished_at": {"type": "string", "format": "date-time"},
    "env": {"type": "string", "enum": ["local", "test", "ci", "prod"]},
    "scope": {"enum": ["module_set", "failing_subset", "full"]},
    "modules": {"type": "array", "minItems": 1,
      "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}},
    "status": {"enum": ["running", "passed", "failed", "budget_exceeded", "escalated"]},
    "retry_budget": {"type": "integer", "minimum": 0, "default": 5},
    "escalation": {
      "type": "object", "additionalProperties": false,
      "required": ["reason_class", "explanation"],
      "properties": {"reason_class": {"$ref": "#/definitions/failure_class"},
                      "explanation": {"type": "string", "minLength": 1}}
    },
    "attempts": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["attempt_number", "result", "failure_class", "summary"],
        "properties": {
          "attempt_number": {"type": "integer", "minimum": 1},
          "result": {"enum": ["pass", "fail"]},
          "failure_class": {"$ref": "#/definitions/failure_class"},
          "summary": {"type": "string", "minLength": 1},
          "diff_ref": {"type": "string",
            "description": "git commit/ stash ref or patch file id capturing this cycle's changes"}
        }
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"enum": ["passed", "failed", "budget_exceeded", "escalated"]}}, "required": ["status"]},
      "then": {"required": ["started_at", "finished_at", "env", "scope"],
                "properties": {"attempts": {"minItems": 1}}}
    },
    {
      "if": {"properties": {"status": {"const": "escalated"}}, "required": ["status"]},
      "then": {"required": ["escalation"]}
    }
  ],
  "definitions": {
    "failure_class": {"enum": ["none", "locator_drift", "timing", "fixture_error",
      "serialization_error", "import_type_error", "data_issue", "environment_unavailable",
      "auth_failure", "backend_5xx", "product_behavior_mismatch", "requirement_conflict",
      "unknown"]}
  }
}
```

## 10. `execution-manifest.json`

Schema: `scripts/schemas/execution_manifest.schema.json`, version `1.1` (ADR-014). This JSON artifact is written beside `run-summary.yaml` under `iterations/<id>/runs/<run-id>/`; it is not a replacement for the run summary. It binds one iteration to the current code SHA, exact command, environment/seed/target summaries, and the expected/collected nodeids. Each attempt independently records its collection, executed nodeids, outcomes, JUnit digest/statistics and Allure digest. A manifest cannot be created from a combined multi-iteration execution: `record-ci-auto` requires `--iteration` and rejects executed nodeids outside that iteration, missing outcomes, skipped/xfailed target nodes, and non-exact JUnit counts. The 1.1 contract is new; no v1 accepted manifest is migrated or silently read as 1.1.

## 11. Plugin source payloads

Schemas: `plugins/_interface/schemas/requirement_source_payload.schema.json`, `plugins/_interface/schemas/api_source_payload.schema.json`.

Plugins emit a **normalized source envelope**, deliberately distinct from internal workflow artifacts — a Zentao connector cannot know the future `iteration_id`/statuses, so internal schemas are wrong at this boundary (review adoption). Envelope shape (success and error variants share one schema; both carry `schema_version`, fixing a v1.3 omission; exactly one of `content` and `error` is required):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object", "additionalProperties": false,
  "required": ["schema_version", "source_type", "fetched_at"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "source_type": {"enum": ["paste", "zentao", "jira", "tapd", "lanhu", "figma"]},
    "fetched_at": {"type": "string", "format": "date-time"},
    "source_ref": {"type": "string"},
    "content": {},
    "attachments": {"type": "array", "items":
      {"type": "object", "additionalProperties": false,
       "required": ["name", "content_ref"],
       "properties": {"name": {"type": "string"}, "content_ref": {"type": "string"}}}},
    "error": {
      "type": "object", "additionalProperties": false,
      "required": ["code", "message"],
      "properties": {"code": {"type": "string"}, "message": {"type": "string"}}
    }
  },
  "oneOf": [
    {"required": ["content"], "not": {"required": ["error"]}},
    {"required": ["error"], "not": {"required": ["content"]}}
  ]
}
```

A successful fetch persists `{...payload}`; a failed fetch persists `{..., error: {code, message}}` instead of raising a raw exception across the boundary — the two variants are mutually exclusive by schema (exactly one of `content` and `error`; `content` may use the source-specific payload shape). The API variant swaps `source_type` enum for `[openapi, har, postman, swagger_ui]` and types `content` more strictly. Conversion into internal artifacts is M1/M4 work — plugins stop at the envelope. `run_plugin.py` persists the envelope to `iterations/<id>/00-raw/source-payload.yaml` **before** validation, keeping the disk-first boundary promise of PRD §2.2; this path is therefore the *quarantine slot*: downstream skills may consume it only after schema validation succeeds, while unrelated raw inputs remain exempt from artifact-schema validation and are revalidated on the exact payload path by pre-commit and CI. **Schema evolution note**: these envelope schemas have never run against a real connector (v1 ships zero plugins); during v1 they may extend **additively only** (new optional fields) without a `schema_version` bump — breaking changes wait for the first real integration (RISKS #17). Security notes (binding even though v1 ships zero real plugins): credentials come from env/config — never hardcoded or returned through the envelope; URL-fetching sources must refuse private/loopback link-local targets; every fetch declares timeout defaults (connect 5s / read 30s) plus response-size and decompression limits enforced by the runner; fetched content is **untrusted data** — instruction-like text inside it is clarification material for M1/M4, never a directive the agent executes, and it never flows verbatim into `knowledge/`.

## 12. What JSON Schema deliberately does not cover

Cross-file and stage-dependent semantics belong to dedicated checkers so schemas stay pure-shape validators:

| Rule | Enforced by | When |
| --- | --- | --- |
| Every referenced R/T/C/A id exists; exemption requirements exist; ids unique per scope; traceability rows resolve | `check_coverage.py` (referential-integrity pass) | every validation run |
| Recorded `automation_test_ids` resolve to *collectable* pytest nodeids (`pytest --collect-only` cross-check against the automation tree) | `check_coverage.py` | staged / CI automation tiers |
| Functional case carries **exactly one** `module:<name>` tag (schema `contains` proves ≥1 only — Draft-07 has no `maxContains`) and declares whole-case `side_effect` | `lint_test_design.py` + `check_functional_expectations.py` | after M3/M6 generation |
| API case carries typed `expected_response.body_assertions[]`; `type` expected matches `value_type`, derived assertions reference a real oracle with matching target/type, and every oracle input has a declared source | `lint_test_design.py` | after M5/M7 generation |
| Run-summary invariants beyond shape: `attempt_number` consecutive and unique from 1; terminal `passed` ⇒ last attempt is a pass; `failed` ⇒ the attempt record documents the execution failure; `escalated` ⇒ `escalation.reason_class` matches the taxonomy and its explanation cites evidence; every repair attempt's `diff_ref` resolves | `validate_iteration.py` semantic pass | pre-commit + CI |
| Execution evidence is exact: one 1.1 manifest per iteration; collection contains expected nodes; executed nodeids and outcomes exactly cover expected nodes; first/retry attempts retain independent JUnit/Allure digests and environment/seed/target summaries | `self_debug_helper.py record-ci-auto --iteration` | E2E evidence write |
| Branch-specific coverage: UI R→T / T→C / C→nodeid, or API R→A / A→nodeid; `manual_only` exemptions stop at the case tier | `check_coverage.py --tier from-iteration` | staged, per PRD §5.1 |
| Endpoint coverage: happy + negative/edge per in-scope endpoint | `check_api_coverage.py` | after M5, PRD §4.4 |
| Functional expectation kind/seed rule; no unexplained numeric or currency literal for `derived_value`; `derived_from.seed` resolves against the seed registry (advisory without one, hard gate from M6); exactly one `module:` tag per case | `check_functional_expectations.py` | after M3/M6 generation |
| Collected automation nodeids are not orphans: every test's `(iteration, case_id)` markers resolve against the owning iteration's cases and its `traceability.yaml` rows (reverse closure — no untracked hand-written tests) | `check_orphan_tests.py` | static-checks + verification battery |
| Client fields are a subset of source schema fields; variables resolve to seed/path/previous response | `check_api_models.py` + API semantic pass | after M5/M7 generation |
| Legal iteration-state transitions; approval/event completeness; latest stage decision and current artifact SHA-256 match for requirements/test-points/exemptions gates; reopen/staleness (`stale` statuses computed from the full hash chain — every `generated_from` input listed on an artifact, scalar form counting as one) | `validate_iteration.py` + `record_approval.py` + `reopen_iteration.py` | pre-commit + CI |
| Exported implies ≥1 case; `.xmind` tree is iteration→module→R→T→C→step; `.xlsx` columns match the API export contract | exporter round-trip tests + CI byte-repro check | CI |
| Retired nodeids are not active coverage; at most one in-progress iteration exists in v1 | `check_coverage.py` + `validate_iteration.py` | every validation run |

Schema registry (binding filename→schema) lives in `scripts/schema_registry.yaml`; `validate_schema.py` refuses any iterations-tree YAML whose path is not registered — new artifact types must register before they can validate.
