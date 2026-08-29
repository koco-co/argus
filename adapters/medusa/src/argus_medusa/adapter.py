"""Medusa 项目适配器：只声明项目事实，不拥有控制面状态。"""

from __future__ import annotations

from urllib.parse import urlsplit

from argus_core.models import Surface, Workstream  # pyright: ignore[reportMissingImports]
from argus_plugin_sdk.contracts import PluginManifest  # pyright: ignore[reportMissingImports]
from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class MedusaConfig(BaseModel):
    """不含密码的项目连接配置；真实凭据由运行环境注入。"""

    model_config = ConfigDict(extra="forbid")

    storefront_url: str = Field(min_length=1)
    store_api_url: str = Field(min_length=1)
    environment: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,31}$")

    @field_validator("storefront_url", "store_api_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Medusa endpoint must use http or https")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("Medusa endpoint must not contain credentials, query, or fragment")
        return value.rstrip("/")


class _SurfaceAdapter:
    """将受信任的项目 base URL 与显式绝对路径拼接。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def url(self, path: str) -> str:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("Medusa route must be an absolute path without query or fragment")
        return f"{self.base_url}{path}"


class MedusaWebAdapter(_SurfaceAdapter):
    """Storefront 路由适配器；不执行浏览器操作。"""


class MedusaAPIAdapter(_SurfaceAdapter):
    """Store API 路由适配器；不执行请求或持有 API 凭据。"""


class MedusaAdapter:
    """为 Argus 提供 Medusa 的 workstream、路由和 connector 元数据。"""

    name = "medusa"
    version = "0.2.0"
    plugin_manifest = PluginManifest(
        name="medusa",
        version=version,
        source_types=["medusa-store-api", "medusa-storefront"],
        capabilities=["api", "requirements"],
    )

    def __init__(self, config: MedusaConfig | None = None) -> None:
        self.config = self.validate_config(config) if config is not None else None

    def workstreams(self) -> tuple[Workstream, Workstream]:
        return (
            Workstream(id="medusa-web", surface=Surface.WEB, metadata={"adapter": self.name}),
            Workstream(id="medusa-api", surface=Surface.API, metadata={"adapter": self.name}),
        )

    @property
    def web(self) -> MedusaWebAdapter:
        if self.config is None:
            raise ValueError("MedusaAdapter requires config before URL access")
        return MedusaWebAdapter(self.config.storefront_url)

    @property
    def api(self) -> MedusaAPIAdapter:
        if self.config is None:
            raise ValueError("MedusaAdapter requires config before URL access")
        return MedusaAPIAdapter(self.config.store_api_url)

    @staticmethod
    def validate_config(config: MedusaConfig) -> MedusaConfig:
        """只校验非秘密 URL/环境形状，不探测或修改靶应用。"""
        return MedusaConfig.model_validate(config)
