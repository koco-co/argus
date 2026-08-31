#!/usr/bin/env python
"""停止 Medusa 靶应用并默认删除其专属数据卷。"""

from __future__ import annotations

import argparse

from _target_app import RUNTIME_ENV, TARGET_DIR, compose


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-volumes", action="store_true", help="保留本地调试数据卷")
    args = parser.parse_args(argv)
    command = ["down", "--remove-orphans"]
    if not args.keep_volumes:
        command.insert(1, "--volumes")
    compose(command)
    if not args.keep_volumes:
        RUNTIME_ENV.unlink(missing_ok=True)
        (TARGET_DIR / "seed-state.yaml").unlink(missing_ok=True)
    print("Medusa 靶应用已停止" + ("，数据卷已保留" if args.keep_volumes else "，数据卷已删除"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
