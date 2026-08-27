# Data Model

Version: 1.3 · Schema contracts updated after the Claude and Grok review adoptions.

Authoritative machine contracts for every YAML artifact crossing a layer boundary. Architecture §1's validation layer enforces these; PRD §2–§5 defines their business meaning. Field-level rules not expressible in JSON Schema (cross-file references, ID uniqueness, staged coverage) live in the **semantic checks** listed in §11 and are enforced by scripts, not prose.

Conventions for all persisted artifacts:

- Top-level `schema_version: "1.0"` is mandatory everywhere.
- Status enums are lowercase snake_case fileside (GLOSSARY).
- Unless stated otherwise, objects set `"additionalProperties": false` — unknown fields fail validation. This is deliberate drift protection.
- IDs follow GLOSSARY formats. Uniqueness scopes differ per artifact; see each entity's "ID" line.

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

Resolved ambiguity entries are **audit evidence and are retained**, not deleted; PRD §4.1's earlier "no ambiguity entries remain" wording is superseded by this document (kept-with-resolution). The two status conditionals together enforce: clarified/accepted ⇒ no unresolved entries; clarifying ⇒ at least one question outstanding (prevents skipping the asking step).

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

Semantic checks: each requirement has at most one exemption; `not_testable` removes it from R→T/R→A demand and `manual_only` permits the case tier but removes it from the automation tier. An accepted UI iteration requires every requirement to have a test point or exemption. An accepted API iteration requires every non-exempt requirement to appear in at least one API case's `requirement_ids[]`.

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
      "requirements_clarifying", "requirements_accepted",
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
    "artifacts": {
      "type": "object", "additionalProperties": false,
      "required": ["requirements", "test_points", "functional_cases",
                    "api_spec", "api_cases", "web_automation", "api_automation", "execution"],
      "properties": {
        "requirements":    {"$ref": "#/definitions/artifact_status"},
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
          "stage": {"enum": ["requirements", "test_points", "environment", "skill_change", "acceptance"]},
          "action": {"enum": ["accepted", "rejected", "provided", "approved"]},
          "actor": {"enum": ["user"]},
          "timestamp": {"type": "string", "format": "date-time"},
          "artifact_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "note": {"type": "string"}
        }
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
          "triggered_by": {"enum": ["agent", "script", "user"]}
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
    "artifact_status": {
      "type": "object", "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {"enum": ["not_started", "draft", "clarifying", "clarified", "accepted",
                             "review", "validating", "valid", "exported", "generating",
                             "linting", "generated", "spec_draft", "spec_valid",
                             "cases_draft", "cases_valid", "running", "passed",
                             "budget_exceeded", "escalated", "stale"]},
        "input_sha256": {"type": ["string", "null"]}
      }
    }
  }
}
```

Semantic check (scripts, not schema): transitions follow PRD §5 routes; v1 requires exactly one of `branches.ui` and `branches.api` to be true, while the both-true Hybrid route is reserved for post-v1; `blocked` clears only via user action; stale propagation rewrites artifact statuses to `stale`.

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

Schema: `.agents/skills/functional-test-design/schemas/functional_cases.schema.json`. Now complete (v1.0 deferred to "as previously specified", which pointed nowhere — fixed).

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
            "contains": {"type": "string", "pattern": "^module:[a-z][a-z0-9_]*$"},
            "maxContains": 1
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

The `module:` tag drives `automation/web/{pages,tests}/<module>/` placement downstream (PRD §4.5) — exactly one required, hence `contains` + `maxContains`.

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
          {"if": {"properties": {"out_of_scope": {"const": true}}},
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
        "enum": {"type": "array", "minItems": 1},
        "required": {"type": "array", "items": {"type": "string"}},
        "properties": {"type": "object", "additionalProperties": {"$ref": "#/definitions/schema_fragment"}},
        "items": {"$ref": "#/definitions/schema_fragment"}
      },
      "oneOf": [{"required": ["type"]}, {"required": ["$ref"]}]
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

## 7. `api/cases.yaml`

Schema: `.agents/skills/api-test-design/schemas/api_cases.schema.json`. Fixes vs v1.0: `iteration_id` declared in properties (was required-but-undefined), lifecycle status names align with the global state machine, `module` is mandatory (it determines generation paths), every case cites its `operation_id` and `requirement_ids[]`, and requests preserve replayable variable sources.

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
                            "body_includes": {"type": "object"}}
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
        "enum": {"type": "array", "minItems": 1},
        "required": {"type": "array", "items": {"type": "string"}},
        "properties": {"type": "object", "additionalProperties": {"$ref": "#/definitions/schema_fragment"}},
        "items": {"$ref": "#/definitions/schema_fragment"}
      },
      "oneOf": [{"required": ["type"]}, {"required": ["$ref"]}]
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
            "items": {"type": "string", "pattern": "^automation/.+::[^:]+$"}
          },
          "retires_nodeids": {
            "type": "array",
            "items": {"type": "string", "pattern": "^automation/.+::[^:]+$"}
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

JSON Schema validates *shape*; `check_coverage.py` enforces semantics per branch and tier (§11). UI updates are idempotent upserts keyed on `(iteration_id, requirement_id, test_point_id?, functional_case_id?)`; API updates are keyed on `(iteration_id, requirement_id, api_case_id)`. Retired nodeids remain auditable in `retires_nodeids[]` and are excluded from active automation coverage. Concurrent-looking repeated writes converge to one row, no duplicates.

## 9. `run-summary.yaml`

Schema: `scripts/schemas/run_summary.schema.json`. Adds the `run_id` promised by PRD §2.1, timing, scope, and the failure-class taxonomy that powers M9's escalation logic.

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
    "status": {"enum": ["running", "passed", "budget_exceeded", "escalated"]},
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
  "definitions": {
    "failure_class": {"enum": ["none", "locator_drift", "timing", "fixture_error",
      "serialization_error", "import_type_error", "data_issue", "environment_unavailable",
      "auth_failure", "backend_5xx", "product_behavior_mismatch", "requirement_conflict",
      "unknown"]}
  }
}
```

## 10. Plugin source payloads

Schemas: `plugins/_interface/schemas/requirement_source_payload.schema.json`, `plugins/_interface/schemas/api_source_payload.schema.json`.

Plugins emit a **normalized source envelope**, deliberately distinct from internal workflow artifacts — a Zentao connector cannot know the future `iteration_id`/statuses, so internal schemas are wrong at this boundary (review adoption). Envelope shape:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object", "additionalProperties": false,
  "required": ["source_type", "fetched_at", "content"],
  "properties": {
    "source_type": {"enum": ["paste", "zentao", "jira", "tapd", "lanhu", "figma"]},
    "fetched_at": {"type": "string", "format": "date-time"},
    "source_ref": {"type": "string"},
    "content": {},
    "attachments": {"type": "array", "items":
      {"type": "object", "additionalProperties": false,
       "required": ["name", "content_ref"],
       "properties": {"name": {"type": "string"}, "content_ref": {"type": "string"}}}}
  }
}
```

The API variant swaps `source_type` enum for `[openapi, har, postman, swagger_ui]` and types `content` more strictly. Conversion into internal artifacts is M1/M4 work — plugins stop at the envelope. `run_plugin.py` persists the envelope to `iterations/<id>/00-raw/source-payload.yaml` **before** validation, keeping the disk-first boundary promise of PRD §2.2; the exact source-payload path is also revalidated by pre-commit and CI, while unrelated raw inputs remain exempt from artifact-schema validation. Security notes (binding even though v1 ships zero real plugins): credentials come from env/config — never hardcoded or returned through the envelope; URL-fetching sources must refuse private/loopback link-local targets; every fetch declares timeout defaults (connect 5s / read 30s); errors return `{error: {code, message}}` shaped payloads rather than raising raw exceptions across the boundary.

## 11. What JSON Schema deliberately does not cover

Cross-file and stage-dependent semantics belong to dedicated checkers so schemas stay pure-shape validators:

| Rule | Enforced by | When |
| --- | --- | --- |
| Every referenced R/T/C/A id exists; exemption requirements exist; ids unique per scope; traceability rows resolve | `check_coverage.py` (referential-integrity pass) | every validation run |
| Branch-specific coverage: UI R→T / T→C / C→nodeid, or API R→A / A→nodeid; `manual_only` exemptions stop at the case tier | `check_coverage.py --tier from-iteration` | staged, per PRD §5.1 |
| Endpoint coverage: happy + negative/edge per in-scope endpoint | `check_api_coverage.py` | after M5, PRD §4.4 |
| Functional expectation kind/seed rule; no unexplained numeric or currency literal for `derived_value` | `check_functional_expectations.py` | after M3/M6 generation |
| Client fields are a subset of source schema fields; variables resolve to seed/path/previous response | `check_api_models.py` + API semantic pass | after M5/M7 generation |
| Legal iteration-state transitions; approval/event completeness; reopen/staleness (`stale` statuses computed from hash chain) | `validate_iteration.py` + `record_approval.py` + `reopen_iteration.py` | pre-commit + CI |
| Exported implies ≥1 case; `.xmind` tree is iteration→module→R→T→C→step; `.xlsx` columns match the API export contract | exporter round-trip tests + CI byte-repro check | CI |
| Retired nodeids are not active coverage; at most one in-progress iteration exists in v1 | `check_coverage.py` + `validate_iteration.py` | every validation run |

Schema registry (binding filename→schema) lives in `scripts/schema_registry.yaml`; `validate_schema.py` refuses any iterations-tree YAML whose path is not registered — new artifact types must register before they can validate.
