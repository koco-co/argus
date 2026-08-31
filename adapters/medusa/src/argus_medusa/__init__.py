"""Argus 的 Medusa 参考项目适配器。"""

from .adapter import (  # pyright: ignore[reportMissingImports]
    MedusaAdapter,
    MedusaAPIAdapter,
    MedusaConfig,
    MedusaWebAdapter,
)

__version__ = "0.2.0"

__all__ = [
    "MedusaAPIAdapter",
    "MedusaAdapter",
    "MedusaConfig",
    "MedusaWebAdapter",
]
