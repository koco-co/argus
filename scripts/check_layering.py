#!/usr/bin/env python
"""Layer dependency checker (Roadmap 1.14 / ARCHITECTURE §3).

Import scan over Python directories only, per the §3 dependency table:

- plugins/     must not import automation, iterations, or .agents/skills
               internals (import names 'automation' / 'iterations' /
               'agents' / 'skills')
- shared/      must not import scripts, plugins, .agents/skills internals
- automation/  must not import scripts, iterations, or .agents/skills
               internals (shared/ and the pytest stack are allowed)

Plus the AST path-literal scan: inside automation/** (and shared/**, whose
NOT-column bars iterations/** at runtime) any string literal referencing
``iterations/`` in a read-shaped context (open/Path/read_text and plain
literals) fails - long-lived assets never read iteration data at test time.

Skills (.agents/skills/**) are Markdown and cannot be import-scanned; a
lightweight grep for direct platform-SDK usage there is wired as an
ADVISORY WARNING that never changes the exit code (process rule, ARCH §3).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

FORBIDDEN_IMPORTS: dict[str, set[str]] = {
    "plugins": {"automation", "iterations", "agents", "skills"},
    "shared": {"scripts", "plugins", "agents", "skills"},
    "automation": {"scripts", "agents", "skills", "iterations"},
}
PATH_LITERAL_LAYERS = {"automation", "shared"}
_ITERATIONS_LITERAL = re.compile(r"(^|[\s\"'_(/])iterations/")
_SKILLS_ADVISORY = re.compile(
    r"\b(?:import|from)\s+(?:playwright|appium|selenium)\b|"
    r"\b(?:playwright|appium)\s*\.\s*(?:sync_api|async_api|chromium)\b"
)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.warnings: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def layer_of(path: Path) -> str | None:
    parts = path.parts
    for layer in ("plugins", "scripts", "shared", "automation"):
        if layer in parts:
            return layer
    return None


def _imported_toplevel(tree) -> list[tuple[int, str, int]]:
    """(lineno, top-level module name, is_from_import) for absolute imports."""
    import ast

    names: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append((node.lineno, alias.name.split(".")[0], 0))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append((node.lineno, node.module.split(".")[0], 1))
    return names


def check_imports(path: Path, layer: str, tree, report: Report) -> None:
    forbidden = FORBIDDEN_IMPORTS.get(layer, set())
    for lineno, top_level, _kind in _imported_toplevel(tree):
        if top_level in forbidden:
            report.fail(
                f"{path}:{lineno}: forbidden layer edge {layer} -> {top_level} "
                f"(ARCHITECTURE §3 dependency table)"
            )


def check_path_literals(path: Path, layer: str, source: str, report: Report) -> None:
    import ast

    if layer not in PATH_LITERAL_LAYERS:
        return
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        literal: str | None = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literal = node.value
        elif isinstance(node, ast.JoinedStr):
            fragments: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    fragments.append(value.value)
            literal = "".join(fragments)
        if literal and _ITERATIONS_LITERAL.search(literal):
            lineno = getattr(node, "lineno", 0)
            report.fail(
                f"{path}:{lineno}: {layer}/ code references iterations/ paths in a "
                f"literal ({literal!r}) - long-lived assets never read iteration data "
                f"at runtime (ARCHITECTURE §3)"
            )


def check_skills_advisory(skills_dir: Path, report: Report) -> None:
    """Process-rule grep for skills - advisory warning only, never fatal."""
    if not skills_dir.is_dir():
        return
    for path in sorted(skills_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _SKILLS_ADVISORY.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            report.warn(
                f"advisory: skills markdown {path}:{line_number} looks like direct "
                f"platform-SDK usage - skills must invoke platforms only via "
                f"scripts/run_plugin.py (process rule, verified by review)"
            )


def scan_python(path: Path, report: Report) -> None:
    import ast

    layer = layer_of(path)
    if layer is None:
        return
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    check_imports(path, layer, tree, report)
    check_path_literals(path, layer, source, report)


def all_python_targets() -> list[Path]:
    targets: list[Path] = []
    for directory in ("plugins", "scripts", "shared", "automation"):
        targets.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="Python files to scan")
    parser.add_argument("--all", action="store_true", help="scan all Python layers")
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        targets.extend(all_python_targets())
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    for path in targets:
        if path.is_file():
            scan_python(path, report)
    check_skills_advisory(REPO_ROOT / ".agents" / "skills", report)

    for warning in report.warnings:
        print(f"layering warning: {warning}", file=sys.stderr)
    for problem in report.problems:
        print(f"layering violation: {problem}")
    if report.problems:
        print(f"check_layering: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_layering: {len(targets)} file(s) clean, {len(report.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
