"""Roadmap 8.1：M12 知识条目必须具备来源且不是空模板。"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _frontmatters(path: Path) -> list[dict[str, object]]:
    parts = path.read_text(encoding="utf-8").split("---")
    return [yaml.safe_load(parts[index]) for index in range(1, len(parts), 2)]


def test_each_knowledge_file_has_evidence_backed_entries() -> None:
    for name in ("patterns.md", "anti-patterns.md"):
        entries = _frontmatters(REPO_ROOT / "knowledge" / name)
        assert entries
        for entry in entries:
            assert set(entry) == {"tags", "date", "source"}
            assert entry["tags"]
            assert entry["date"]
            assert "commit:" in str(entry["source"])


def test_knowledge_entries_are_not_duplicated() -> None:
    for name in ("patterns.md", "anti-patterns.md"):
        text = (REPO_ROOT / "knowledge" / name).read_text(encoding="utf-8")
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        assert len(headings) == len(set(headings))
