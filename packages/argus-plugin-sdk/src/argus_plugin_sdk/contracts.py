"""版本化来源连接器契约。

连接器只返回不可信 source envelope；它们不能写 iteration、调用 Skill 或访问模型。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def timezone_aware_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("datetime fields must include a timezone")
        return value


class SourceError(_ContractModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class SourceEnvelope(_ContractModel):
    """严格二选一的 source payload；成功与错误不能同时存在。"""

    schema_version: Literal["2.0"] = "2.0"
    source_type: str = Field(min_length=1, max_length=100)
    fetched_at: datetime
    source_ref: str | None = None
    content: Any = None
    error: SourceError | None = None

    @model_validator(mode="before")
    @classmethod
    def exactly_one_result(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("source envelope must be an object")
        has_content = "content" in value
        has_error = "error" in value
        if has_content == has_error:
            raise ValueError("source envelope requires exactly one of content or error")
        return value


class PluginManifest(_ContractModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    source_types: list[str] = Field(min_length=1)
    capabilities: list[Literal["requirements", "api", "issues", "openapi"]] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_capabilities(self) -> PluginManifest:
        if len(set(self.source_types)) != len(self.source_types):
            raise ValueError("source_types must be unique")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capabilities must be unique")
        return self


class PluginContext(_ContractModel):
    """凭据仅存在于内存上下文，且不参与 repr/JSON 导出。"""

    credentials: Mapping[str, str] = Field(default_factory=dict, repr=False)
    max_bytes: int = Field(default=8 * 1024 * 1024, ge=1)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    read_timeout_seconds: float = Field(default=30.0, gt=0)

    @model_serializer(mode="wrap")
    def without_credentials(self, handler: Any) -> dict[str, Any]:
        serialized = handler(self)
        serialized.pop("credentials", None)
        return serialized


class SourcePlugin(Protocol):
    manifest: PluginManifest

    def fetch(self, source_ref: str, *, context: PluginContext) -> SourceEnvelope:
        """读取来源并返回 source envelope；不得写入项目工件。"""
        ...
