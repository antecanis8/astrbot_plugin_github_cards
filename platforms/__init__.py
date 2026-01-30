"""Platform abstraction layer for multi-platform support."""

from .base import PlatformProvider, RepoInfo, IssueInfo, PRInfo

# Platform registry - will be populated when platform modules are imported
PLATFORMS: dict[str, "PlatformProvider"] = {}


def register_platform(provider: "PlatformProvider") -> None:
    """Register a platform provider."""
    PLATFORMS[provider.name] = provider


__all__ = [
    "PlatformProvider",
    "RepoInfo",
    "IssueInfo",
    "PRInfo",
    "PLATFORMS",
    "register_platform",
]
