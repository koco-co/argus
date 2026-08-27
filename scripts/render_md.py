#!/usr/bin/env python
"""Deterministic markdown renderer for iteration artifacts (Roadmap 1.4).

Renders ``requirements.yaml`` → ``requirement.md`` and ``test_points.yaml``
→ ``test_points.md`` as derived views (ADR-007: never hand-edited, never LLM
freeform output). Determinism contract (PRD §6): the bytes are a pure
function of the source YAML — no timestamps, no locale, stable ordering —
so two runs over unchanged input are byte-identical.

Sources are validated through the shared registry path before rendering;
invalid sources stop with a non-zero exit. Missing sources are skipped
(artifacts appear as their owning skills produce them).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path


def _fmt_priority(value: Any) -> str:
    return str(value) if value is not None else "2"  # DATA_MODEL §2: absent reads as 2


def render_requirements(doc: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Requirements — {doc['iteration_id']}",
        "",
        f"Status: `{doc['status']}`",
        "",
    ]
    for requirement in doc["requirements"]:
        lines.append(f"## {requirement['requirement_id']} — {requirement['title']}")
        lines.append("")
        lines.append(requirement["description"])
        lines.append("")
        lines.append(f"- priority: {_fmt_priority(requirement.get('priority'))}")
        if requirement.get("source"):
            lines.append(f"- source: {requirement['source']}")
        lines.append("")
    ambiguities = doc.get("ambiguities", [])
    if ambiguities:
        lines.append("## Ambiguities")
        lines.append("")
        for ambiguity in ambiguities:
            state = "resolved" if ambiguity.get("resolved") else "open"
            lines.append(f"- [{state}] {ambiguity['question']}")
            if ambiguity.get("resolution"):
                lines.append(f"  - resolution: {ambiguity['resolution']}")
        lines.append("")
    return "\n".join(lines)


def render_test_points(doc: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Test Points — {doc['iteration_id']}",
        "",
        f"Status: `{doc['status']}`",
        "",
    ]
    for point in doc["test_points"]:
        lines.append(
            f"## {point['test_point_id']} — {point['type']} (P{point.get('priority', '—')})"
        )
        lines.append("")
        lines.append(point["description"])
        lines.append("")
        lines.append(f"- requirements: {', '.join(point['requirement_ids'])}")
        lines.append("")
    return "\n".join(lines)


RENDERERS: dict[str, tuple[str, Callable[[dict[str, Any]], str]]] = {
    "requirements.yaml": ("requirement.md", render_requirements),
    "test_points.yaml": ("test_points.md", render_test_points),
}


def render_iteration(iteration_dir: Path) -> list[Path]:
    """Render every present, registered source; returns written paths."""
    written: list[Path] = []
    for source_name, (output_name, renderer) in RENDERERS.items():
        source = iteration_dir / source_name
        if not source.exists():
            continue
        validate_path(source)  # schema-gated before any derived view is written
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        output = iteration_dir / output_name
        output.write_text(renderer(document), encoding="utf-8")
        written.append(output)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    if not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1
    try:
        written = render_iteration(iteration_dir)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not written:
        print("render_md: nothing to render (no registered sources present)")
        return 0
    for path in written:
        print(f"render_md: wrote {path.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
