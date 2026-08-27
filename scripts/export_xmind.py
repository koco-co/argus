#!/usr/bin/env python
"""XMind exporter (Roadmap 1.5) — renders functional-cases.yaml into
``<Project>_v<N>_Cases.xmind`` under the iteration's ``exports/`` directory.

Format: XMind ZEN-family zip layout (content.json + metadata.json +
manifest.json). Byte-reproducibility contract (PRD §6): ZIP entry timestamps
and document properties are pinned, so two runs over unchanged input produce
identical SHA-256. Exporters overwrite nothing — the ``<N>`` version is the
highest existing version in the same exports/ dir plus one, starting at 1
(GLOSSARY "Export filenames").

Tree contract (DATA_MODEL §5): ``iteration → module → requirement (R####) →
test point (T####) → functional case (C####) → step``; IDs and titles are
preserved at each node; a case linked to several requirements/test points
appears under each applicable source path. Sources are schema-gated through
the shared registry before any derived view is written; cases must have
reached ``valid``/``exported`` status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path

PROJECT = REPO_ROOT.name
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
FILENAME_PATTERN = re.compile(rf"^{PROJECT}_v(\d+)_Cases\.xmind$")
CASES_READY = {"valid", "exported"}


def topic(node_id: str, title: str, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": node_id, "title": title}
    if children:
        entry["children"] = {"attached": children}
    return entry


def build_tree(
    requirements: dict[str, Any], test_points: dict[str, Any], cases: dict[str, Any]
) -> dict[str, Any]:
    by_requirement = {r["requirement_id"]: r for r in requirements["requirements"]}
    by_point = {p["test_point_id"]: p for p in test_points["test_points"]}
    by_case = {c["case_id"]: c for c in cases["cases"]}

    # module -> requirement -> test point -> cases (deduplicated, sorted)
    tree: dict[str, dict[str, dict[str, list[str]]]] = {}
    for case in sorted(by_case.values(), key=lambda c: c["case_id"]):
        module = next(t.split("module:", 1)[1] for t in case["tags"] if t.startswith("module:"))
        for point_id in sorted(case["test_point_ids"]):
            point = by_point[point_id]
            for requirement_id in sorted(point["requirement_ids"]):
                module_entry = tree.setdefault(module, {})
                requirement_entry = module_entry.setdefault(requirement_id, {})
                requirement_entry.setdefault(point_id, []).append(case["case_id"])

    module_topics = []
    for module in sorted(tree):
        requirement_topics = []
        for requirement_id in sorted(tree[module]):
            requirement = by_requirement[requirement_id]
            point_topics = []
            for point_id in sorted(tree[module][requirement_id]):
                point = by_point[point_id]
                case_topics = []
                for case_id in tree[module][requirement_id][point_id]:
                    case = by_case[case_id]
                    step_topics = [
                        topic(f"step-{case['case_id']}-{number}", step["action"])
                        for number, step in enumerate(case["steps"], start=1)
                    ]
                    case_topics.append(topic(f"case-{case_id}", case["title"], step_topics))
                point_topics.append(
                    topic(f"point-{point_id}", f"{point_id} — {point['description']}", case_topics)
                )
            requirement_topics.append(
                topic(
                    f"req-{requirement_id}",
                    f"{requirement_id} — {requirement['title']}",
                    point_topics,
                )
            )
        module_topics.append(topic(f"module-{module}", module, requirement_topics))

    sheet = {
        "id": f"sheet-{cases['iteration_id']}",
        "class": "sheet",
        "title": cases["iteration_id"],
        "rootTopic": topic(
            f"iteration-{cases['iteration_id']}", cases["iteration_id"], module_topics
        ),
    }
    return sheet


def render_content(sheet: dict[str, Any]) -> str:
    return json.dumps([sheet], ensure_ascii=False, indent=2, sort_keys=True)


def render_support_files() -> tuple[str, str]:
    metadata = {
        "dataStructureVersion": "zen",
        "creator": {"name": PROJECT, "version": "1.0"},
    }
    manifest = {
        "file-entries": {"content.json": {}, "metadata.json": {}},
    }
    return (
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    )


def write_xmind(destination: Path, content_json: str) -> None:
    metadata_json, manifest_json = render_support_files()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ("content.json", content_json),
            ("metadata.json", metadata_json),
            ("manifest.json", manifest_json),
        ):
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)


def next_version(exports_dir: Path) -> int:
    highest = 0
    if exports_dir.is_dir():
        for existing in exports_dir.glob(f"{PROJECT}_v*_Cases.xmind"):
            match = FILENAME_PATTERN.match(existing.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def load_tree_sources(iteration_dir: Path) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for name in ("requirements.yaml", "test_points.yaml", "functional-cases.yaml"):
        path = iteration_dir / name
        if not path.exists():
            raise RegistryError(f"missing source for export: {path}")
        validate_path(path)
        sources[name] = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases_status = sources["functional-cases.yaml"]["status"]
    if cases_status not in CASES_READY:
        raise RegistryError(
            f"functional-cases.yaml status is {cases_status!r}; export requires "
            f"{'/'.join(sorted(CASES_READY))} (PRD §4.3)"
        )
    return sources


def verify_structure(xmind_path: Path) -> dict[str, Any]:
    """Re-open the written file and assert the zip→content.json layout plus
    the iteration→module→R→T→C→step hierarchy. Returns the parsed sheet."""
    with zipfile.ZipFile(xmind_path) as archive:
        names = set(archive.namelist())
        assert {"content.json", "metadata.json", "manifest.json"} <= names
        sheet = json.loads(archive.read("content.json"))[0]
    root = sheet["rootTopic"]

    def children_of(node: dict[str, Any]) -> list[dict[str, Any]]:
        return node.get("children", {}).get("attached", [])

    modules = children_of(root)
    assert modules, "no module level under the iteration root"
    for module_node in modules:
        requirements = children_of(module_node)
        assert requirements, f"module {module_node['title']} has no requirement level"
        for requirement_node in requirements:
            assert re.match(r"^req-R[0-9]{4}$", requirement_node["id"])
            points = children_of(requirement_node)
            assert points, f"requirement {requirement_node['id']} has no test point level"
            for point_node in points:
                cases = children_of(point_node)
                assert cases, f"test point {point_node['id']} has no case level"
                for case_node in cases:
                    steps = children_of(case_node)
                    assert steps, f"case {case_node['id']} has no step level"
    return sheet


def export(iteration_dir: Path) -> Path:
    sources = load_tree_sources(iteration_dir)
    sheet = build_tree(
        sources["requirements.yaml"],
        sources["test_points.yaml"],
        sources["functional-cases.yaml"],
    )
    exports_dir = iteration_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    version = next_version(exports_dir)
    destination = exports_dir / f"{PROJECT}_v{version}_Cases.xmind"
    write_xmind(destination, render_content(sheet))
    verify_structure(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    if not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1
    try:
        destination = export(iteration_dir)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"export_xmind: wrote {destination.relative_to(REPO_ROOT).as_posix()} (sha256 {digest})")
    return 0
