"""Local model routing presets."""

from craik.runtime.local_models.presets import (
    LOCAL_MODEL_PRESETS,
    LocalModelHealth,
    LocalModelPreset,
    check_local_model_health,
    list_local_model_presets,
    local_model_base_url_warnings,
    provider_for_local_model_preset,
    require_local_model_preset,
)

__all__ = [
    "LOCAL_MODEL_PRESETS",
    "LocalModelHealth",
    "LocalModelPreset",
    "check_local_model_health",
    "list_local_model_presets",
    "local_model_base_url_warnings",
    "provider_for_local_model_preset",
    "require_local_model_preset",
]
