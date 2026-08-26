from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    mode: str
    llm_available: bool
    status: str
    reason: str | None

    def payload(self) -> dict[str, object]:
        return asdict(self)


class LLMProvider(Protocol):
    """Provider-neutral boundary for future planning and answer generation adapters."""

    def health(self) -> ProviderHealth: ...


class DeterministicFallbackProvider:
    """Safe demo fallback; it never sends engineering data to an external model."""

    def health(self) -> ProviderHealth:
        configured = os.getenv("ASSISTANT_LLM_PROVIDER", "disabled").strip().lower()
        if configured == "disabled":
            reason = "LLM_PROVIDER_DISABLED"
        else:
            reason = "LLM_PROVIDER_ADAPTER_NOT_CONFIGURED"
        return ProviderHealth(
            provider="deterministic-demo",
            mode="deterministic_fallback",
            llm_available=False,
            status="degraded",
            reason=reason,
        )


def get_assistant_provider() -> LLMProvider:
    # Stage 6 deliberately keeps the fallback as the only executable adapter. A provider-specific
    # adapter can be added behind this boundary without changing the Assistant response contract.
    return DeterministicFallbackProvider()
