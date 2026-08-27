"""Roadmap 1.1 DoD: every fenced JSON Schema block in DATA_MODEL.md must
extract and parse — documentation drift breaks the build instead of hiding.

The committed .schema.json files additionally incorporate the documented
`generated_from.inputs[]` extension (DATA_MODEL intro), so they are a strict
superset of the fenced blocks; this test pins the doc side.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_MODEL = REPO_ROOT / "docs/spec/architecture/DATA_MODEL.md"

# §2 requirements · §2.1 exemptions · §3 iteration · §4 test_points · §5
# functional_cases · §6 api_spec · §7 api_cases · §8 traceability · §9
# run_summary · §10 source payload envelope.
EXPECTED_BLOCK_COUNT = 10


def extract_fenced_json_schemas(markdown: str) -> list[dict]:
    blocks = re.findall(r"```json\n(.*?)```", markdown, flags=re.DOTALL)
    return [json.loads(block) for block in blocks]


def test_every_data_model_json_block_parses_as_draft07_schema() -> None:
    blocks = extract_fenced_json_schemas(DATA_MODEL.read_text(encoding="utf-8"))
    assert len(blocks) == EXPECTED_BLOCK_COUNT, (
        f"DATA_MODEL fenced JSON Schema block count changed: {len(blocks)} != "
        f"{EXPECTED_BLOCK_COUNT} — update this test with the doc change"
    )
    for index, schema in enumerate(blocks, start=1):
        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#", f"block #{index}"
        assert schema.get("type") == "object", f"block #{index}"


def test_committed_schemas_are_doc_superset_via_inputs_extension() -> None:
    """`generated_from` in committed artifact schemas carries the optional
    `inputs[]` sibling (DATA_MODEL intro), which the fenced blocks predate."""
    schema_paths = sorted(
        p
        for p in (
            REPO_ROOT / ".agents" / "skills" / "*" / "schemas" / "*.schema.json",
            REPO_ROOT / "scripts" / "schemas" / "*.schema.json",
            REPO_ROOT / "plugins" / "_interface" / "schemas" / "*.schema.json",
        )
        for p in p.parent.glob(p.name)
    )
    with_generated_from = [
        p
        for p in schema_paths
        if "generated_from" in json.loads(p.read_text(encoding="utf-8")).get("definitions", {})
    ]
    assert with_generated_from, "no committed schema defines generated_from"
    for path in with_generated_from:
        schema = json.loads(path.read_text(encoding="utf-8"))
        properties = schema["definitions"]["generated_from"]["properties"]
        assert "inputs" in properties, f"{path.name} missing generated_from.inputs[] extension"
