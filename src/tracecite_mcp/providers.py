"""Host-owned process-local EvidenceProvider registry.

The registry resolves provider names into already constructed provider objects.
It is not an Agent tool and never imports domain implementations automatically.
"""

from __future__ import annotations

from threading import RLock
from typing import Iterable

from tracecite.extension.retrieval import EvidenceProvider


_LOCK = RLock()
_PROVIDERS: dict[str, EvidenceProvider] = {}


def _provider_name(provider: EvidenceProvider) -> str:
    name = str(getattr(provider, "name", "") or "").strip()
    if not name or len(name) > 128:
        raise ValueError("provider name must be 1-128 characters")
    return name


def register_provider(provider: EvidenceProvider, *, replace: bool = False) -> str:
    """Register a process-local provider at the Host boundary."""
    if not isinstance(provider, EvidenceProvider):
        raise TypeError("provider must satisfy TraceCite EvidenceProvider")
    name = _provider_name(provider)
    with _LOCK:
        if name in _PROVIDERS and not replace:
            raise ValueError(f"provider already registered: {name}")
        _PROVIDERS[name] = provider
    return name


def registered_provider_names() -> tuple[str, ...]:
    with _LOCK:
        return tuple(sorted(_PROVIDERS))


def resolve_providers(names: Iterable[str]) -> tuple[EvidenceProvider, ...]:
    requested = tuple(
        dict.fromkeys(str(item).strip() for item in names if str(item).strip())
    )
    if not requested:
        raise ValueError("at least one provider_name is required")
    with _LOCK:
        missing = [name for name in requested if name not in _PROVIDERS]
        if missing:
            raise ValueError(f"unknown host provider(s): {', '.join(missing)}")
        return tuple(_PROVIDERS[name] for name in requested)


def clear_providers() -> None:
    """Clear the process-local registry; primarily useful for Host tests."""
    with _LOCK:
        _PROVIDERS.clear()
