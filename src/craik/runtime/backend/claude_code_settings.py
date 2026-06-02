"""Claude Code model and project settings helpers."""

from __future__ import annotations

import re
from pathlib import Path

from craik.contracts.models import ProjectProfile
from craik.runtime.auth.profile import CredentialKind
from craik.runtime.auth.store import AuthProfileStore, AuthProfileStoreError
from craik.runtime.backend.claude_code_attestations import _claude_model_arg
from craik.runtime.modeling import ModelSettingsStore
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore


def _project_for_cwd(store: LocalStore) -> ProjectProfile:
    registry = ProjectRegistry(store)
    return registry.add_project(Path.cwd())


def _title_from_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if not normalized:
        return "TUI run"
    return normalized[:60].rstrip(" .,;:") or "TUI run"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _active_model(env: dict[str, str] | None) -> str:
    active_model = ModelSettingsStore.from_env(env).load().active_model
    return active_model or "anthropic/claude-sonnet-4-20250514"


def anthropic_uses_claude_cli_marker(env: dict[str, str] | None) -> bool:
    provider_id, _model = _active_provider_and_model(env)
    if provider_id != "provider_anthropic":
        return False
    try:
        profile = AuthProfileStore.from_env(env).get("anthropic:default")
    except AuthProfileStoreError:
        return False
    return (
        profile.kind is CredentialKind.MARKER
        and profile.metadata.get("external_runtime") == "claude-cli"
    )


def _active_provider_and_model(env: dict[str, str] | None) -> tuple[str, str | None]:
    settings = ModelSettingsStore.from_env(env).load()
    active_profile = settings.active_profile
    if active_profile is not None:
        return active_profile.provider_id, active_profile.model
    active_model = settings.active_model
    if not active_model:
        return "provider_openai", None
    provider_name = active_model.split("/", 1)[0]
    model = active_model.split("/", 1)[1] if "/" in active_model else None
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
    return provider_id, model


# Per-vendor permission-mode env vars + their REAL CLI mode vocabularies.
# Each surface reads ITS OWN env var so the operator's chosen mode reaches the
# matching vendor CLI faithfully (capture, don't force). The mode sets are the
# values verified against the installed CLIs (see the validators below):
#   claude: --permission-mode {default, acceptEdits, plan, dontAsk, bypassPermissions}
#   gemini: --approval-mode    {default, auto_edit, yolo, plan}
#   codex:  --sandbox          {read-only, workspace-write, danger-full-access}
CLAUDE_PERMISSION_MODE_ENV = "CRAIK_CLAUDE_PERMISSION_MODE"
GEMINI_APPROVAL_MODE_ENV = "CRAIK_GEMINI_APPROVAL_MODE"
CODEX_SANDBOX_MODE_ENV = "CRAIK_CODEX_SANDBOX_MODE"

_CLAUDE_PERMISSION_MODES = ("default", "acceptEdits", "plan", "dontAsk", "bypassPermissions")
_GEMINI_APPROVAL_MODES = ("default", "auto_edit", "yolo", "plan")
_CODEX_SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")


def _claude_permission_mode(env: dict[str, str] | None) -> str | None:
    values = env or {}
    mode = values.get(CLAUDE_PERMISSION_MODE_ENV)
    return mode if mode in _CLAUDE_PERMISSION_MODES else None


def _gemini_approval_mode(env: dict[str, str] | None) -> str | None:
    """Return the Gemini CLI ``--approval-mode`` value, or ``None`` if unset/invalid.

    Reads ``CRAIK_GEMINI_APPROVAL_MODE`` and returns it only when it is one of
    the REAL Gemini CLI approval modes (``gemini --help`` -> ``--approval-mode
    [choices: default, auto_edit, yolo, plan]``). ``yolo`` is the high-risk
    bypass-equivalent. Anything else (a Claude/Codex mode, junk) -> ``None``, so
    a foreign mode never reaches the gemini argv.
    """
    values = env or {}
    mode = values.get(GEMINI_APPROVAL_MODE_ENV)
    return mode if mode in _GEMINI_APPROVAL_MODES else None


def _codex_sandbox_mode(env: dict[str, str] | None) -> str | None:
    """Return the codex CLI ``--sandbox`` value, or ``None`` if unset/invalid.

    Reads ``CRAIK_CODEX_SANDBOX_MODE`` and returns it only when it is one of the
    REAL codex sandbox modes (``codex exec --help`` -> ``-s/--sandbox [possible
    values: read-only, workspace-write, danger-full-access]``).
    ``danger-full-access`` is the high-risk bypass-equivalent. Codex is
    observe-only: craik passes the mode so the CLI behaves, but cannot live-gate
    it. Anything else -> ``None``, so a foreign mode never reaches the codex argv.
    """
    values = env or {}
    mode = values.get(CODEX_SANDBOX_MODE_ENV)
    return mode if mode in _CODEX_SANDBOX_MODES else None


def _claude_code_command_summary(env: dict[str, str] | None) -> str:
    model = _active_model(env)
    parts = ["claude", "--tools", "default", "--output-format", "stream-json", "--verbose"]
    model_arg = _claude_model_arg(model)
    if model_arg:
        parts.extend(["--model", model_arg])
    permission_mode = _claude_permission_mode(env)
    if permission_mode:
        parts.extend(["--permission-mode", permission_mode])
    parts.extend(["-p", "<compiled Craik prompt>"])
    return " ".join(parts)
