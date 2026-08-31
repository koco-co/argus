"""允许用 ``python -m argus_core`` 调用控制面 CLI。"""

from .cli import main  # pyright: ignore[reportMissingImports]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
