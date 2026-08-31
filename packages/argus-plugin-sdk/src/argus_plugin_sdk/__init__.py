"""Argus 0.2 source-plugin contract; not an Agent Runtime."""

from .connectors import OpenAPIReferenceConnector  # pyright: ignore[reportMissingImports]
from .contracts import (  # pyright: ignore[reportMissingImports]
    PluginContext,
    PluginManifest,
    SourceEnvelope,
    SourceError,
    SourcePlugin,
)
from .github import GitHubIssuesConnector  # pyright: ignore[reportMissingImports]
from .registry import (  # pyright: ignore[reportMissingImports]
    PluginRegistry,
    PluginRegistryError,
    default_registry,
)

__version__ = "0.2.0"

__all__ = [
    "GitHubIssuesConnector",
    "OpenAPIReferenceConnector",
    "PluginContext",
    "PluginManifest",
    "PluginRegistry",
    "PluginRegistryError",
    "SourceEnvelope",
    "default_registry",
    "SourceError",
    "SourcePlugin",
]
