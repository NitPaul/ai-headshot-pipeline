"""Image generation back-ends."""

from __future__ import annotations

from typing import Any

from .base import ImageProvider, ProviderError, QuotaExhausted


def build_provider(cfg: Any) -> ImageProvider:
    name = str(cfg.provider.name).lower()
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(cfg)
    if name == "manual":
        from .manual import ManualProvider

        return ManualProvider(cfg)
    if name == "stub":
        from .stub import StubProvider

        return StubProvider(cfg)
    raise ProviderError(
        f"Unknown provider '{name}' in config.yaml. "
        "Use 'manual', 'gemini' or 'stub'."
    )


__all__ = [
    "ImageProvider",
    "ProviderError",
    "QuotaExhausted",
    "build_provider",
]
