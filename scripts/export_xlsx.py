#!/usr/bin/env python
"""XLSX exporter for API cases (Roadmap 1.6) — renders api/cases.yaml into
``<Project>_v<N>_API_Cases.xlsx`` under the iteration's ``exports/`` dir.

Column contract (DATA_MODEL §7): ``api_case_id, module, operation_id, method,
endpoint, case_type, title, request.path_params, request.query,
request.headers, request.body, request.variables,
expected_response.status_code, expected_response.body_schema,
expected_response.body_includes``.

Byte-reproducibility contract (PRD §6): workbook document properties
(created/modified) are pinned and every ZIP entry of the resulting package is
rewritten with a fixed timestamp, so two runs over unchanged input produce
identical bytes. Versioning follows GLOSSARY: highest existing ``<N>`` in the
same exports/ dir plus one, starting at 1 — nothing is overwritten. Sources
are schema-gated through the shared registry; export refuses cases not in
``cases_valid``/``exported``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path
from openpyxl import Workbook, load_workbook

PROJECT = REPO_ROOT.name
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
FIXED_DATETIME = datetime(1980, 1, 1, 0, 0, 0)
FILENAME_PATTERN = re.compile(rf"^{PROJECT}_v(\d+)_API_Cases\.xlsx$")
CASES_READY = {"cases_valid", "exported"}

COLUMNS = [
    "api_case_id",
    "module",
    "operation_id",
    "method",
    "endpoint",
    "case_type",
    "title",
    "request.path_params",
    "request.query",
    "request.headers",
    "request.body",
    "request.variables",
    "expected_response.status_code",
    "expected_response.body_schema",
    "expected_response.body_includes",
]


def cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def row_for(case: dict[str, Any]) -> list[str]:
    request = case.get("request") or {}
    expected = case.get("expected_response") or {}
    return [
        cell_value(case.get("api_case_id")),
        cell_value(case.get("module")),
        cell_value(case.get("operation_id")),
        cell_value(case.get("method")),
        cell_value(case.get("endpoint")),
        cell_value(case.get("case_type")),
        cell_value(case.get("title")),
        cell_value(request.get("path_params")),
        cell_value(request.get("query")),
        cell_value(request.get("headers")),
        cell_value(request.get("body")),
        cell_value(request.get("variables")),
        cell_value(expected.get("status_code")),
        cell_value(expected.get("body_schema")),
        cell_value(expected.get("body_includes")),
    ]


def next_version(exports_dir: Path) -> int:
    highest = 0
    if exports_dir.is_dir():
        for existing in exports_dir.glob(f"{PROJECT}_v*_API_Cases.xlsx"):
            match = FILENAME_PATTERN.match(existing.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def deterministic_xlsx_bytes(workbook: Workbook) -> bytes:
    workbook.properties.created = FIXED_DATETIME
    workbook.properties.modified = FIXED_DATETIME
    buffer = io.BytesIO()
    workbook.save(buffer)
    inner = zipfile.ZipFile(buffer)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        for info in inner.infolist():
            pinned = zipfile.ZipInfo(info.filename, date_time=FIXED_DATE)
            pinned.compress_type = zipfile.ZIP_DEFLATED
            pinned.external_attr = info.external_attr
            payload = inner.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl 在 save() 内部强制把 modified 改回当前时间，必须在
                # 最终 ZIP 层再次固定，否则跨秒两次导出的字节不同。
                payload = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>1980-01-01T00:00:00Z\g<2>",
                    payload,
                )
            archive.writestr(pinned, payload)
    return outer.getvalue()


def export(iteration_dir: Path) -> Path:
    cases_path = iteration_dir / "api" / "cases.yaml"
    if not cases_path.exists():
        raise RegistryError(f"missing source for export: {cases_path}")
    validate_path(cases_path)
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    status = document["status"]
    if status not in CASES_READY:
        raise RegistryError(
            f"api/cases.yaml status is {status!r}; export requires "
            f"{'/'.join(sorted(CASES_READY))} (PRD §4.4)"
        )

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None  # a new workbook always has one active sheet
    sheet.title = "API Cases"
    sheet.append(COLUMNS)
    for case in sorted(document["cases"], key=lambda c: c["api_case_id"]):
        sheet.append(row_for(case))

    exports_dir = iteration_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    version = next_version(exports_dir)
    destination = exports_dir / f"{PROJECT}_v{version}_API_Cases.xlsx"
    destination.write_bytes(deterministic_xlsx_bytes(workbook))
    return destination


def round_trip(path: Path) -> tuple[list[str], list[list[Any]]]:
    workbook = load_workbook(path)
    sheet = workbook.active
    assert sheet is not None
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(cell) for cell in rows[0]]
    return header, [list(row) for row in rows[1:]]


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
    try:
        display_path = destination.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        display_path = destination.as_posix()
    print(f"export_xlsx: wrote {display_path} (sha256 {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
