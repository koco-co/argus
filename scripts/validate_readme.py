"""严格校验仓库 README 的标题、编码和本地链接。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
_IGNORED_PARTS = {".git", ".venv", "node_modules", "build", "dist"}
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\n]+)\)")
_HTML_HREF = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE)


def discover_readmes(root: Path = REPO_ROOT) -> list[Path]:
    """发现仓库内 README，排除依赖和构建目录。"""
    return sorted(
        path
        for path in root.rglob("README.md")
        if not any(part in _IGNORED_PARTS for part in path.relative_to(root).parts)
    )


def _link_target(raw: str) -> tuple[str, str | None] | None:
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None
    if parsed.path == "":
        return None
    return unquote(parsed.path), parsed.fragment or None


def validate_readme(path: Path, *, root: Path = REPO_ROOT, strict: bool = False) -> list[str]:
    """返回单个 README 的问题；strict 模式还限制链接不得越出 root。"""
    errors: list[str] = []
    label = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}: cannot read UTF-8 content ({exc.__class__.__name__})"]

    if strict:
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first.startswith("# "):
            errors.append(f"{label}: first non-empty line must be a level-1 Markdown heading")

    raw_targets = [match.group(1) for match in _MARKDOWN_LINK.finditer(text)]
    raw_targets.extend(match.group(2) for match in _HTML_HREF.finditer(text))
    for raw in raw_targets:
        parsed = _link_target(raw)
        if parsed is None:
            continue
        link_path, _fragment = parsed
        candidate = (path.parent / link_path).resolve()
        if strict and not candidate.is_relative_to(root.resolve()):
            errors.append(f"{label}: local link escapes repository root: {raw.strip()!r}")
        elif not candidate.exists():
            errors.append(f"{label}: local link does not exist: {raw.strip()!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", type=Path, help="要检查的 README；默认检查仓库内全部 README"
    )
    parser.add_argument("--strict", action="store_true", help="将标题、越界链接和缺失链接视为错误")
    args = parser.parse_args(argv)

    paths = args.paths or discover_readmes()
    errors: list[str] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
        if not path.is_file():
            errors.append(f"{raw_path}: README file does not exist")
            continue
        errors.extend(validate_readme(path.resolve(), root=REPO_ROOT, strict=args.strict))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"README 校验失败：{len(errors)} 个问题", file=sys.stderr)
        return 1
    print(f"README 校验通过：{len(paths)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
