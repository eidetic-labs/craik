"""Provider Gateway event helpers."""

from __future__ import annotations

from craik.runtime.backend.events import BackendEvent
from craik.runtime.modeling import ModelProfile, readable_model_name
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_runner import ProviderBackedRunResult


def provider_default_model(provider_id: str) -> str | None:
    provider = default_model_provider_registry().get(provider_id)
    if provider is None:
        return None
    default_model = provider.metadata.get("default_model")
    return default_model if isinstance(default_model, str) and default_model else None


def provider_family(provider_id: str) -> str | None:
    provider = default_model_provider_registry().get(provider_id)
    if provider is None:
        return None
    return provider.provider


def model_display_name(
    *,
    provider_id: str,
    model: str | None,
    profile: ModelProfile | None,
) -> str:
    if profile is not None and profile.display_name:
        return profile.display_name
    provider = default_model_provider_registry().get(provider_id)
    provider_name = provider.name if provider is not None else provider_id
    if model:
        family = provider.provider if provider is not None else provider_id
        return readable_model_name(family, model)
    return provider_name


def provider_tool_call_events(
    result: ProviderBackedRunResult,
    *,
    run_id: str,
    task_id: str,
) -> list[BackendEvent]:
    events: list[BackendEvent] = []
    for index, provider_result in enumerate(result.provider_results, start=1):
        for call in provider_result.tool_calls:
            if not isinstance(call, dict):
                continue
            tool = call.get("name") or call.get("tool") or call.get("type")
            tool_name = str(tool) if tool else "provider_tool"
            events.append(
                BackendEvent(
                    type="tool.used",
                    run_id=run_id,
                    task_id=task_id,
                    data={
                        "provider_id": provider_result.provider_id,
                        "provider_family": provider_result.provider_family,
                        "model": provider_result.model,
                        "response_id": provider_result.response_id,
                        "tool": tool_name,
                        "target": tool_name,
                        "message": (
                            f"{provider_result.provider_family} provider used `{tool_name}` "
                            f"during step {index}."
                        ),
                    },
                )
            )
    return events
