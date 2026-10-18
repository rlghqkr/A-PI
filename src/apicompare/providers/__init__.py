"""Provider 어댑터 레지스트리. 어댑터 모듈은 필요할 때만 import 한다(SDK 하나가 없어도 나머지는 동작)."""

from __future__ import annotations

from importlib import import_module

from .base import ProviderAdapter

_REGISTRY: dict[str, tuple[str, str]] = {
    "openai": ("apicompare.providers.openai_adapter", "OpenAIAdapter"),
    "anthropic": ("apicompare.providers.anthropic_adapter", "AnthropicAdapter"),
    "gemini": ("apicompare.providers.gemini_adapter", "GeminiAdapter"),
}


def get_adapter(name: str, **kwargs) -> ProviderAdapter:
    """get_adapter("openai", timeout_s=30, max_retries=0, api_key=None, admin_key=None, default_model=None)"""
    if name not in _REGISTRY:
        raise KeyError(f"알 수 없는 provider: {name} (가능: {list(_REGISTRY)})")
    module_name, class_name = _REGISTRY[name]
    cls = getattr(import_module(module_name), class_name)
    return cls(**kwargs)


__all__ = ["ProviderAdapter", "get_adapter"]
