"""Small persisted model selection settings for v0.10.0 UX."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from craik.runtime.paths import ensure_craik_home
from craik.runtime.providers.provider_transport import normalize_provider_family


@dataclass(frozen=True)
class ModelProfile:
    """Named provider/model profile with provider-specific options."""

    id: str
    provider_id: str
    provider_family: str
    model: str
    display_name: str
    backend: str = "provider"
    options: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "model": self.model,
            "display_name": self.display_name,
            "backend": self.backend,
            "options": self.options,
        }


@dataclass(frozen=True)
class ModelSettings:
    """Active model, aliases, and fallback order."""

    active_model: str | None = None
    active_profile_id: str | None = None
    profiles: dict[str, ModelProfile] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "active_model": self.active_model,
            "active_profile_id": self.active_profile_id,
            "profiles": {key: profile.as_dict() for key, profile in self.profiles.items()},
            "aliases": self.aliases,
            "fallbacks": self.fallbacks,
        }

    @property
    def active_profile(self) -> ModelProfile | None:
        """Return the selected profile, if one is persisted."""
        if self.active_profile_id is None:
            return None
        return self.profiles.get(self.active_profile_id)


class ModelSettingsStore:
    """File-backed model settings scoped to the active Craik home."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ModelSettingsStore:
        paths = ensure_craik_home(env)
        return cls(paths.config / "model-settings.json")

    def load(self) -> ModelSettings:
        if not self.path.exists():
            return ModelSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        aliases = payload.get("aliases", {})
        fallbacks = payload.get("fallbacks", [])
        profiles = payload.get("profiles", {})
        settings = ModelSettings(
            active_model=_string_or_none(payload.get("active_model")),
            active_profile_id=_string_or_none(payload.get("active_profile_id")),
            profiles=_profiles_from_payload(profiles),
            aliases=aliases if isinstance(aliases, dict) else {},
            fallbacks=[str(item) for item in fallbacks] if isinstance(fallbacks, list) else [],
        )
        return _repair_active_profile(settings)

    def save(self, settings: ModelSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=".model-settings.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings.as_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def model_profile_from_ref(
    model_ref: str,
    *,
    display_name: str | None = None,
    backend: str = "provider",
    options: dict[str, object] | None = None,
) -> ModelProfile:
    """Create a persisted model profile from a <provider>/<model> selector."""
    provider_name, model = model_ref.split("/", 1)
    provider_id, provider_family = _provider_identity(provider_name)
    profile_id = _profile_id(provider_family, model, options or {})
    return ModelProfile(
        id=profile_id,
        provider_id=provider_id,
        provider_family=provider_family,
        model=model,
        display_name=display_name or _display_name(provider_family, model, options or {}),
        backend=backend,
        options=options or {},
    )


def _profiles_from_payload(value: object) -> dict[str, ModelProfile]:
    if not isinstance(value, dict):
        return {}
    profiles: dict[str, ModelProfile] = {}
    for key, raw_profile in value.items():
        if not isinstance(key, str) or not isinstance(raw_profile, dict):
            continue
        provider_id = _string_or_none(raw_profile.get("provider_id"))
        provider_family = _string_or_none(raw_profile.get("provider_family"))
        model = _string_or_none(raw_profile.get("model"))
        display_name = _string_or_none(raw_profile.get("display_name"))
        if provider_id is None or provider_family is None or model is None or display_name is None:
            continue
        options = raw_profile.get("options", {})
        options = options if isinstance(options, dict) else {}
        profiles[key] = ModelProfile(
            id=_string_or_none(raw_profile.get("id")) or key,
            provider_id=provider_id,
            provider_family=provider_family,
            model=model,
            display_name=_repair_display_name(provider_family, model, display_name, options),
            backend=_string_or_none(raw_profile.get("backend")) or "provider",
            options=options,
        )
    return profiles


def _repair_active_profile(settings: ModelSettings) -> ModelSettings:
    """Hydrate model profile metadata for settings written before profiles existed."""
    if settings.active_model is None or settings.active_profile is not None:
        return settings
    try:
        profile = model_profile_from_ref(settings.active_model)
    except ValueError:
        return settings
    return ModelSettings(
        active_model=settings.active_model,
        active_profile_id=profile.id,
        profiles={**settings.profiles, profile.id: profile},
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )


def _provider_identity(provider_name: str) -> tuple[str, str]:
    provider_id = {
        "anthropic": "provider_anthropic",
        "claude": "provider_anthropic",
        "openai": "provider_openai",
        "gemini": "provider_google",
        "google": "provider_google",
        "openai-compatible": "provider_local_openai_compatible",
        "local": "provider_local_openai_compatible",
        "ollama": "provider_local_ollama",
        "lm-studio": "provider_local_lm_studio",
        "vllm": "provider_local_vllm",
    }.get(provider_name, provider_name)
    family = {
        "provider_anthropic": "anthropic",
        "provider_openai": "openai",
        "provider_google": "google",
        # Legacy provider-id in persisted records still resolves to the google family.
        "provider_gemini": "google",
        "provider_local_openai_compatible": "local",
        "provider_local_ollama": "ollama",
        "provider_local_lm_studio": "lm-studio",
        "provider_local_vllm": "vllm",
    }.get(provider_id, provider_name)
    return provider_id, family


def _profile_id(provider_family: str, model: str, options: dict[str, object]) -> str:
    effort = options.get("reasoning_effort")
    suffix = f"-{effort}" if isinstance(effort, str) and effort else ""
    return f"{provider_family}-{_slug(model)}{suffix}"


def _display_name(provider_family: str, model: str, options: dict[str, object]) -> str:
    effort = options.get("reasoning_effort")
    effort_label = f" {str(effort).title()}" if isinstance(effort, str) and effort else ""
    return f"{readable_model_name(provider_family, model)}{effort_label}"


def readable_model_name(provider_family: str, model: str) -> str:
    """Return a human-oriented model label while preserving the raw id elsewhere."""
    normalized_family = provider_family.replace("_", "-").lower()
    canonical_family = normalize_provider_family(normalized_family)
    if normalized_family == "anthropic":
        return _readable_anthropic_model(model)
    if normalized_family == "openai":
        return _readable_openai_model(model)
    if canonical_family == "google":
        # role-2: the model NAME parser still inspects "gemini-..." tokens.
        return _readable_gemini_model(model)
    provider_label = {
        "ollama": "Ollama",
        "lm-studio": "LM Studio",
        "vllm": "vLLM",
        "local": "Local",
        "chat-completions": "Local",
        "chat_completions": "Local",
    }.get(normalized_family, provider_family.replace("_", " ").replace("-", " ").title())
    readable_model = _title_model_tokens(model)
    return f"{provider_label} {readable_model}" if readable_model else provider_label


def _readable_anthropic_model(model: str) -> str:
    model_id = _strip_provider_prefix(model)
    tokens = _drop_date_suffix(model_id.split("-"))
    if tokens and tokens[0] == "claude":
        tokens = tokens[1:]
    if not tokens:
        return "Claude"
    family = tokens[0].title()
    version = _version_from_tokens(tokens[1:])
    return f"Claude {family} {version}".strip()


def _readable_openai_model(model: str) -> str:
    model_id = _strip_provider_prefix(model)
    if model_id.startswith("gpt-"):
        return f"GPT-{model_id.removeprefix('gpt-').upper()}"
    return _title_model_tokens(model_id)


def _readable_gemini_model(model: str) -> str:
    model_id = _strip_provider_prefix(model)
    tokens = model_id.split("-")
    if tokens and tokens[0] == "gemini":
        tokens = tokens[1:]
    suffix = _title_model_tokens("-".join(tokens))
    return f"Gemini {suffix}".strip()


def _title_model_tokens(model: str) -> str:
    return " ".join(_readable_token(token) for token in model.replace(":", "-").split("-") if token)


def _readable_token(token: str) -> str:
    lower = token.lower()
    if lower.startswith("gpt"):
        return token.upper()
    if lower.startswith("llama") and len(lower) > len("llama"):
        return f"Llama {token[len('llama') :]}"
    if lower in {"pro", "mini", "preview", "turbo", "instruct"}:
        return lower.title()
    return token.upper() if token.isupper() else token.title()


def _version_from_tokens(tokens: list[str]) -> str:
    version_parts: list[str] = []
    labels: list[str] = []
    for token in tokens:
        if token.isdigit() or _is_decimal(token):
            version_parts.append(token)
        else:
            labels.append(_readable_token(token))
    version = ".".join(version_parts)
    label = " ".join(labels)
    return " ".join(part for part in [version, label] if part)


def _drop_date_suffix(tokens: list[str]) -> list[str]:
    if tokens and len(tokens[-1]) == 8 and tokens[-1].isdigit():
        return tokens[:-1]
    return tokens


def _strip_provider_prefix(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


def _is_decimal(value: str) -> bool:
    return bool(value) and all(part.isdigit() for part in value.split("."))


def _repair_display_name(
    provider_family: str,
    model: str,
    display_name: str,
    options: dict[str, object],
) -> str:
    legacy_name = _legacy_display_name(provider_family, model, options)
    if display_name == legacy_name:
        return _display_name(provider_family, model, options)
    return display_name


def _legacy_display_name(provider_family: str, model: str, options: dict[str, object]) -> str:
    provider_label = {
        "anthropic": "Anthropic Claude",
        "openai": "OpenAI",
        "google": "Google Gemini",
        "gemini": "Google Gemini",
        "ollama": "Ollama",
        "lm-studio": "LM Studio",
        "vllm": "vLLM",
        "local": "Local OpenAI-compatible",
    }.get(
        normalize_provider_family(provider_family),
        provider_family.replace("_", " ").title(),
    )
    effort = options.get("reasoning_effort")
    effort_label = f" {str(effort).title()}" if isinstance(effort, str) and effort else ""
    return f"{provider_label} {model}{effort_label}"


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value.lower()).strip(
        "-"
    )
