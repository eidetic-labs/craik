"""Interactive and one-shot Craik shell helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable

from craik.runtime.auth import AuthProfileStore, CredentialKind
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.dispatch import invoke_slash_command as _contract_invoke
from craik.runtime.i18n.messages import text as localize_text
from craik.runtime.providers.model_providers import (
    ModelProviderNotFoundError,
    default_model_provider_registry,
)
from craik.runtime.providers.provider_runtime import (
    ProviderMessage,
    ProviderRuntimeRequest,
    adapter_for_provider,
)
from craik.runtime.shell.contract_runtime.builtin_slash_commands import run_command
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.model_settings import ModelSettingsStore
from craik.runtime.shell.readiness import ReadinessReport, resolve_readiness


def render_status_card(report: ReadinessReport, *, env: dict[str, str] | None = None) -> str:
    """Render a compact launch status card."""
    lines = [
        localize_text("shell.title", env=env),
        f"{localize_text('shell.state', env=env)}: {report.state}",
        f"{localize_text('shell.home', env=env)}: {report.home}",
        f"{localize_text('shell.profile', env=env)}: {report.active_profile}",
        f"{localize_text('shell.model', env=env)}: "
        f"{report.active_model or localize_text('shell.not_selected', env=env)}",
    ]
    if report.missing:
        lines.append(f"{localize_text('shell.missing', env=env)}: {', '.join(report.missing)}")
    if report.warnings:
        lines.extend(
            f"{localize_text('shell.warning', env=env)}: {warning}"
            for warning in report.warnings
        )
    lines.append(f"{localize_text('shell.next_actions', env=env)}:")
    lines.extend(f"- {action}" for action in report.next_actions)
    lines.append(localize_text("shell.help_hint", env=env))
    return "\n".join(lines)


def one_shot_response(prompt: str, *, env: dict[str, str] | None = None) -> str:
    """Return the final one-shot shell response without extra shell decoration."""
    report = resolve_readiness(env)
    if report.state != "fully-ready":
        return localize_text(
            "shell.one_shot.not_ready",
            env=env,
            state=report.state,
            next_action=report.next_actions[0],
        )
    try:
        result = _execute_one_shot(prompt, env=env)
    except Exception as error:
        return f"One-shot execution failed: {error}"
    return result


def _execute_one_shot(prompt: str, *, env: dict[str, str] | None = None) -> str:
    settings = ModelSettingsStore.from_env(env).load()
    active_model = settings.active_model
    if active_model is None:
        raise ValueError("no active model is configured")
    provider_id, model = _provider_and_model(active_model)
    provider = default_model_provider_registry().require(provider_id)
    live_enabled = _live_provider_enabled(env)
    if live_enabled and provider.provider == "anthropic" and _anthropic_uses_claude_cli(env):
        return _execute_claude_cli_prompt(prompt, model=model, env=env)
    adapter = adapter_for_provider(provider, live_enabled=live_enabled)
    adapter.config.model = model
    result = adapter.execute(
        ProviderRuntimeRequest(
            messages=[ProviderMessage(role="user", content=prompt.strip())],
            stream=False,
            metadata={"surface": "craik.console.one_shot"},
        )
    )
    if result.text.strip():
        return result.text.strip()
    if result.structured_output is not None:
        return str(result.structured_output)
    return f"Completed one-shot execution for {active_model}."


def _provider_and_model(active_model: str) -> tuple[str, str]:
    provider_name, model = active_model.split("/", 1)
    registry = default_model_provider_registry()
    if registry.get(provider_name) is not None:
        return provider_name, model
    provider_id = {
        "anthropic": "provider_anthropic",
        "claude": "provider_anthropic",
        "gemini": "provider_gemini",
        "google": "provider_gemini",
        "openai": "provider_openai",
        "openai-compatible": "provider_local_openai_compatible",
        "local": "provider_local_openai_compatible",
        "ollama": "provider_local_ollama",
        "lm-studio": "provider_local_lm_studio",
        "vllm": "provider_local_vllm",
    }.get(provider_name)
    if provider_id is not None:
        return provider_id, model
    for provider in registry.list():
        if provider.provider == provider_name:
            return provider.id, model
    raise ModelProviderNotFoundError(f"unknown provider in active model: {provider_name}")


def _live_provider_enabled(env: dict[str, str] | None) -> bool:
    values = os.environ if env is None else env
    if values.get("CRAIK_LIVE") == "0":
        return False
    if values.get("CRAIK_FIXTURE") == "1":
        return False
    return True


def _anthropic_uses_claude_cli(env: dict[str, str] | None) -> bool:
    try:
        profile = AuthProfileStore.from_env(env).get("anthropic:default")
    except Exception:
        return False
    return (
        profile.kind is CredentialKind.MARKER
        and profile.metadata.get("external_runtime") == "claude-cli"
    )


def _execute_claude_cli_prompt(
    prompt: str,
    *,
    model: str,
    env: dict[str, str] | None,
) -> str:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude CLI was not found; install Claude Code and run `claude`")
    command = ["claude", "-p", prompt.strip()]
    model_arg = _claude_cli_model_arg(model)
    if model_arg:
        command.extend(["--model", model_arg])
    permission_mode = _claude_cli_permission_mode(env)
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
            env=_claude_cli_env(env),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Claude CLI prompt timed out") from exc
    except OSError as exc:
        raise RuntimeError("Claude CLI could not be executed") from exc
    if completed.returncode != 0:
        detail = _safe_cli_detail(completed.stderr or completed.stdout)
        raise RuntimeError("Claude CLI prompt failed" + (f": {detail}" if detail else ""))
    output = completed.stdout.strip()
    if output:
        return output
    diagnostic = _empty_claude_cli_output_message(prompt, completed.stderr)
    if diagnostic:
        return diagnostic
    return "Claude CLI completed without response text."


def _claude_cli_model_arg(model: str) -> str | None:
    lowered = model.lower()
    if "opus" in lowered:
        return "opus"
    if "sonnet" in lowered:
        return "sonnet"
    if "haiku" in lowered:
        return "haiku"
    return None


def _claude_cli_permission_mode(env: dict[str, str] | None) -> str | None:
    values = os.environ if env is None else env
    mode = values.get("CRAIK_CLAUDE_PERMISSION_MODE")
    if mode in {"default", "acceptEdits", "plan", "auto"}:
        return mode
    return None


def _claude_cli_env(env: dict[str, str] | None) -> dict[str, str]:
    values = dict(os.environ)
    if env is not None:
        values.update(env)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_TOKEN",
        "CRAIK_ANTHROPIC_API_KEY",
    ):
        values.pop(name, None)
    return values


def _safe_cli_detail(output: str) -> str:
    return " ".join(output.split())[:300]


def _empty_claude_cli_output_message(prompt: str, stderr: str | None) -> str:
    lines = [
        "Claude CLI completed but did not return response text.",
        "",
        "This can happen when the delegated `claude -p` run exits without a final stdout "
        "message. For auditable Claude Code tool activity, run the prompt through:",
        "",
        f"/run --backend claude-code {prompt.strip()}",
    ]
    detail = _safe_cli_detail(stderr or "")
    if detail:
        lines.extend(["", f"CLI detail: {detail}"])
    return "\n".join(lines)


def run_shell(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    stdin_isatty: bool | None = None,
    lines: Iterable[str] | None = None,
    registry: AutoSlashRegistry | None = None,
) -> int:
    """Run the Craik shell, falling back to a status card for noninteractive launch."""
    report = resolve_readiness(env)
    output_func(render_status_card(report, env=env))
    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    scripted = iter(lines) if lines is not None else None
    registry = registry or get_tui_registry()
    if not interactive and scripted is None:
        return 0

    while True:
        try:
            raw = next(scripted) if scripted is not None else input_func("craik> ")
        except (EOFError, StopIteration):
            return 0
        text = raw.strip()
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            output_func("Session ended.")
            return 0
        if text.startswith("/"):
            result = to_slash_command_result(
                _contract_invoke(text, registry=registry, env=env)
            )
            output_func(result.text)
            if result.exit_shell:
                return result.exit_code
            continue
        result = to_slash_command_result(run_command(text, env=env))
        output_func(result.text)
