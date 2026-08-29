"""显式、可审计的插件注册表。"""

from __future__ import annotations

from datetime import UTC, datetime

from .contracts import (  # pyright: ignore[reportMissingImports]
    PluginContext,
    PluginManifest,
    SourceEnvelope,
    SourceError,
    SourcePlugin,
)
from .security import contains_secret  # pyright: ignore[reportMissingImports]


class PluginRegistryError(ValueError):
    """注册表拒绝未知、重复或不符合契约的插件。"""


class PluginRegistry:
    """只接受宿主显式注册的插件，不扫描目录、不执行动态文本。"""

    def __init__(self) -> None:
        self._plugins: dict[str, SourcePlugin] = {}
        self._manifests: dict[str, PluginManifest] = {}

    def register(self, plugin: SourcePlugin) -> PluginManifest:
        try:
            manifest = PluginManifest.model_validate(plugin.manifest)
            fetch = plugin.fetch
        except (AttributeError, TypeError, ValueError) as exc:
            raise PluginRegistryError(
                "plugin must expose a valid manifest and fetch method"
            ) from exc
        if not callable(fetch):
            raise PluginRegistryError("plugin fetch must be callable")
        if manifest.name in self._plugins:
            raise PluginRegistryError(f"plugin already registered: {manifest.name}")
        self._plugins[manifest.name] = plugin
        self._manifests[manifest.name] = manifest
        return manifest

    def get(self, name: str) -> SourcePlugin:
        try:
            return self._plugins[name]
        except KeyError as exc:
            raise PluginRegistryError(f"unknown plugin: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))

    def fetch(self, name: str, source_ref: str, *, context: PluginContext) -> SourceEnvelope:
        """执行已注册插件，并将异常、未声明类型和凭据载荷收敛为错误。"""
        plugin = self.get(name)
        manifest = self._manifests[name]
        try:
            envelope = plugin.fetch(source_ref, context=context)
            if not isinstance(envelope, SourceEnvelope):
                raise TypeError("plugin returned a non-envelope value")
            if envelope.source_type not in manifest.source_types:
                raise ValueError("plugin returned an undeclared source_type")
            if contains_secret(envelope.model_dump(mode="python"), context):
                raise ValueError("plugin returned credential-shaped data")
            return envelope
        except Exception as exc:  # noqa: BLE001 - 插件边界不得泄漏异常或凭据
            source_type = manifest.source_types[0]
            return SourceEnvelope(
                source_type=source_type,
                source_ref=source_ref,
                fetched_at=datetime.now(UTC),
                error=SourceErrorPayload.from_exception(exc),
            )


def default_registry() -> PluginRegistry:
    """返回显式注册的参考连接器集合；不扫描入口点或执行动态代码。"""
    from .connectors import OpenAPIReferenceConnector  # pyright: ignore[reportMissingImports]
    from .github import GitHubIssuesConnector  # pyright: ignore[reportMissingImports]

    registry = PluginRegistry()
    registry.register(OpenAPIReferenceConnector())
    registry.register(GitHubIssuesConnector())
    return registry


class SourceErrorPayload:
    """把任意插件异常收敛为不含异常原文的错误模型。"""

    @staticmethod
    def from_exception(exc: Exception) -> SourceError:
        del exc
        return SourceError(code="plugin_failed", message="插件执行失败；请检查连接器日志")
