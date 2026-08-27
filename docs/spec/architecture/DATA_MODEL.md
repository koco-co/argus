# Data Model

Authoritative machine contracts for every YAML artifact crossing a layer boundary. Architecture §1's validation layer enforces these; PRD §2–§5 defines their business meaning. Field-level rules not expressible in JSON Schema (cross-file references, ID uniqueness, staged coverage) live in the **semantic checks** listed in §11 and are enforced by scripts, not prose.

Conventions for all persisted artifacts:

- Top-level `schema_version: "1.0"` is mandatory everywhere.
- Status enums are lowercase snake_case fileside (GLOSSARY).
- Unless stated otherwise, objects set `"additionalProperties": false` — unknown fields fail validation. This is deliberate drift protection.
- IDs follow GLOSSARY formats. Uniqueness scopes differ per artifact; see each entity's "ID" line.

Schema placement follows production ownership: `requirements/test_points/functional_cases` schemas under `.agents/skills/test-design/schemas/`; `api_spec` + `api_cases` under `.agents/skills/api-test-design/schemas/`; `iteration`, `traceability`, `run_summary` under `scripts/schemas/`; `*_source_payload` under `plugins/_interface/schemas/`. Filename↔artifact binding is an explicit registry table (`scripts/schema_registry.yaml`) — never inferred from filename similarity.

## 1. Entity relationships

| Entity | Meaning | Relationship / cardinality | Basis |
| --- | --- | --- | --- |
| IterationState | Aggregate lifecycle record of one iteration | 1 → 0..1 of each workflow artifact in its directory; 1 → N runs | PRD §2.1, §5 |
| Requirement | Clarified unit of demand (R####) | 1 → 1..N TestPoint (unless `testable:false`) | PRD §4.1–4.2 |
| TestPoint | Testable angle on requirement(s) (T####) | 1 → 0..N FunctionalCase | PRD §4.2–4.3 |
| FunctionalCase | Executable manual scenario (C####) | 0..N rows' source in TraceabilityRecord; → AutomationTest(s) | PRD §4.3 |
| NormalizedSpec | Module-tagged endpoint catalog | 1 endpoint → 2..N APICase (happy + negative/edge, unless out-of-scope) | PRD §4.4 |
| APICase | Single API verification (A####) | → AutomationTest(s) | PRD §4.4 |
| AutomationTest | Long-lived pytest node under `automation/` | referenced by traceability nodeids | PRD §4.5–4.6 |
| TraceabilityRecord | Sparse link row per requirement chain | N sparse rows; coverage computed, never hand-written | PRD §3 M10, ADR-005 |
| RunResult | One self-debug invocation outcome | N per iteration | PRD §4.7 |

## 2. `requirements.yaml`

Schema: `.agents/skills/test-design/schemas/requirements.schema.json`. ID: GLOSSARY `requirement_id`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "requirements"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
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
          "source": {"type": "string"},
          "testable": {"type": "boolean", "default": true},
          "not_testable_reason": {"type": "string"},
          "automation_required": {"type": "boolean", "default": true},
          "manual_reason": {"type": "string"}
        },
        "allOf": [
          {"if": {"properties": {"testable": {"const": false}}},
           "then": {"required": ["not_testable_reason"]}},
          {"if": {"properties": {"automation_required": {"const": false}}},
           "then": {"required": ["manual_reason"]}}
        ]
      }
    },
    "ambiguities": {
      "type": "array",
      "items": {"$ref": "#/definitions/ambiguity"}
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"enum": ["clarified", "accepted"]}}, "required": ["status"]},
      "then": {"properties": {"ambiguities": {"items": {"properties": {"resolved": {"const": true"}}}}}}
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
      "properties": {
        "artifact": {"type": "string"},
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
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
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
      "properties": {"ui": {"type": "boolean"}, "api": {"type": "boolean"}}
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

Semantic check (scripts, not schema): transitions follow PRD §5 routes; `blocked` clears only via user action; stale propagation rewrites artifact statuses to `stale`.

## 4. `test_points.yaml`

Schema: `.agents/skills/test-design/schemas/test_points.schema.json`. ID: GLOSSARY `test_point_id`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "test_points"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "status": {"enum": ["draft", "review", "accepted"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "test_points": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["test_point_id", "requirement_ids", "description"],
        "properties": {
          "test_point_id": {"type": "string", "pattern": "^T[0-9]{4}$"},
          "requirement_ids": {"type": "array", "minItems": 1,
            "items": {"type": "string", "pattern": "^R[0-9]{4}$"}},
          "description": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "enum": [1, 2, 3]}
        }
      }
    }
  },
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "properties": {"artifact": {"type": "string"},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

## 5. `functional-cases.yaml`

Schema: `.agents/skills/test-design/schemas/functional_cases.schema.json`. Now complete (v1.0 deferred to "as previously specified", which pointed nowhere — fixed).

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "cases"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "status": {"enum": ["draft", "validating", "valid", "exported"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "cases": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["case_id", "title", "priority", "steps", "tags", "test_point_ids"],
        "properties": {
          "case_id": {"type": "string", "pattern": "^C[0-9]{4}$"},
          "title": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "enum": [1, 2, 3]},
          "precondition": {"type": "string"},
          "steps": {
            "type": "array", "minItems": 1,
            "items": {
              "type": "object", "additionalProperties": false,
              "required": ["action", "expected"],
              "properties": {
                "action": {"type": "string", "minLength": 1},
                "expected": {"type": "string", "minLength": 1}
              }
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
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "properties": {"artifact": {"type": "string"},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

The `module:` tag drives `automation/web/{pages,tests}/<module>/` placement downstream (PRD §4.5) — exactly one required, hence `contains` + `maxContains`.

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
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "status": {"enum": ["spec_draft", "spec_valid"]},
    "service_name": {"type": "string", "minLength": 1},
    "base_path": {"type": "string"},
    "auth_model": {"type": "string"},
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
        "required": ["operation_id", "path", "method", "module"],
        "properties": {
          "operation_id": {"type": "string", "minLength": 1},
          "path": {"type": "string", "pattern": "^/"},
          "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
          "summary": {"type": "string"},
          "module": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
          "authentication": {"type": "string"},
          "path_parameters": {"type": "array", "items": {"$ref": "#/definitions/param"}},
          "query_parameters": {"type": "array", "items": {"$ref": "#/definitions/param"}},
          "request_body": {
            "type": "object", "additionalProperties": false,
            "properties": {"content_type": {"type": "string"}, "example": {}}
          },
          "responses": {"type": "array", "items": {
            "type": "object", "additionalProperties": false,
            "required": ["status_code"],
            "properties": {"status_code": {"type": "integer"}, "description": {"type": "string"}}}},
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
  "definitions": {
    "param": {
      "type": "object", "additionalProperties": false,
      "required": ["name"],
      "properties": {"name": {"type": "string"}, "in": {"type": "string"},
                      "required": {"type": "boolean"}, "example": {}}
    }
  }
}
```

## 7. `api/cases.yaml`

Schema: `.agents/skills/api-test-design/schemas/api_cases.schema.json`. Fixes vs v1.0: `iteration_id` declared in properties (was required-but-undefined), `module` is mandatory (it determines generation paths), `request` gains structure, every case cites its `operation_id`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "iteration_id", "status", "cases"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "status": {"enum": ["draft", "validated", "exported"]},
    "generated_from": {"$ref": "#/definitions/generated_from"},
    "cases": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["api_case_id", "operation_id", "endpoint", "method", "title",
                      "case_type", "module", "request", "expected_response"],
        "properties": {
          "api_case_id": {"type": "string", "pattern": "^A[0-9]{4}$"},
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
              "body": {}
            }
          },
          "expected_response": {
            "type": "object", "additionalProperties": false,
            "required": ["status_code"],
            "properties": {"status_code": {"type": "integer"},
                            "body_schema": {"type": "object"},
                            "body_includes": {"type": "object"}}
          }
        }
      }
    }
  },
  "definitions": {
    "generated_from": {
      "type": "object", "additionalProperties": false,
      "properties": {"artifact": {"type": "string"},
                     "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}
    }
  }
}
```

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
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
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
          }
        }
      }
    }
  }
}
```

JSON Schema validates *shape*; `check_coverage.py` enforces semantics per tier (§11). Updates are idempotent upserts keyed on `(iteration_id, requirement_id, test_point_id, functional_case_id|api_case_id)` — concurrent-looking repeated writes converge to one row, no duplicates.

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
    "iteration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "run_id": {"type": "string", "pattern": "^run-[0-9]{8}T[0-9]{6}Z(-[a-z0-9]{4})?$"},
    "started_at": {"type": "string", "format": "date-time"},
    "finished_at": {"type": "string", "format": "date-time"},
    "env": {"type": "string", "enum": ["local", "test", "prod"]},
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

The API variant swaps `source_type` enum for `[openapi, har, postman, swagger_ui]` and types `content` more strictly. Conversion into internal artifacts is M1/M4 work — plugins stop at the envelope. `run_plugin.py` persists the envelope to `iterations/<id>/00-raw/source-payload.yaml` **before** validation, keeping the disk-first boundary promise of PRD §2.2. Security notes (binding even though v1 ships zero real plugins): credentials come from env/config — never hardcoded or returned through the envelope; URL-fetching sources must refuse private/loopback link-local targets; every fetch declares timeout defaults (connect 5s / read 30s); errors return `{error: {code, message}}` shaped payloads rather than raising raw exceptions across the boundary.

## 11. What JSON Schema deliberately does not cover

Cross-file and stage-dependent semantics belong to dedicated checkers so schemas stay pure-shape validators:

| Rule | Enforced by | When |
| --- | --- | --- |
| Every referenced R/T/C/A id exists; ids unique per scope; traceability rows resolve | `check_coverage.py` (referential-integrity pass) | every validation run |
| Coverage tiers R→T / T→C / C→nodeid, honoring `testable`/`automation_required` flags | `check_coverage.py --tier <t>` | staged, per PRD §5.1 |
| Endpoint coverage: happy + negative/edge per in-scope endpoint | `check_api_coverage.py` | after M5, PRD §4.4 |
| Legal iteration-state transitions; approval/event completeness; staleness (`stale` statuses computed from hash chain) | `validate_iteration.py` state pass | pre-commit + CI |
| Exported implies ≥1 case; exported `.xmind`/`.xlsx` match source content | exporter round-trip tests + CI byte-repro check | CI |

Schema registry (binding filename→schema) lives in `scripts/schema_registry.yaml`; `validate_schema.py` refuses any iterations-tree YAML whose path is not registered — new artifact types must register before they can validate.
