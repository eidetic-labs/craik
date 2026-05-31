"""Provider login and credential-storage CLI commands."""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, NoReturn

import click
import typer

from craik.cli import auth_app
from craik.cli_output import emit_command_result
from craik.runtime.auth import AuthProfileNotFoundError, AuthProfileStore, CredentialKind
from craik.runtime.auth.login import (
    AuthCaptureResult,
    capture_and_cache_login,
    explicit_reference_login,
    logout_provider,
    migrate_env_profiles,
)
from craik.runtime.auth.oauth_provider_login import (
    OAuthLoginResult,
    anthropic_claude_cli_login,
    browser_oauth_login,
    google_oauth_login,
)
from craik.runtime.auth.sources.anthropic_claude_cli import AnthropicClaudeCliError
from craik.runtime.auth.sources.anthropic_oauth import AnthropicOAuthError
from craik.runtime.auth.sources.google_oauth import GoogleOAuthError
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthError
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.providers.provider_transport import normalize_provider_family
from craik.runtime.providers.provider_url_safety import ProviderURLSafetyError
from craik.runtime.shell.credential_storage import credential_storage_status
from craik.runtime.shell.readiness import resolve_readiness

storage_app = typer.Typer(help="Inspect and migrate credential storage posture.")
auth_app.add_typer(storage_app, name="storage")

DEFAULT_CLAUDE_CLI_PROVIDERS = {"anthropic"}
DEFAULT_OAUTH_PROVIDERS = {"google"}


@auth_app.command("login")
@craik_command(
    payload_shape="card",
    interactive_prompts={"reauthenticate": "ConfirmModal"},
)
def auth_login_provider(
    provider: Annotated[
        str,
        typer.Argument(
            help=(
                "Provider family: openai, anthropic, google, or local "
                "(gemini accepted as a legacy alias)."
            ),
        ),
    ] = "openai",
    no_browser: Annotated[
        bool,
        typer.Option(
            "--no-browser",
            help="Do not launch provider/browser setup.",
        ),
    ] = False,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Login mode: api-key or oauth."),
    ] = None,
    profile_id: Annotated[
        str | None,
        typer.Option("--profile-id", help="Auth profile id to create."),
    ] = None,
    env_var: Annotated[
        str | None,
        typer.Option("--env-var", help="Environment variable containing the provider key."),
    ] = None,
    secret_ref: Annotated[
        str | None,
        typer.Option("--secret-ref", help="Secret reference instead of an environment variable."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Provider base URL for local-compatible providers."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="GCP project id for Gemini/Vertex OAuth profiles."),
    ] = None,
    service_account: Annotated[
        Path | None,
        typer.Option(
            "--service-account",
            help="Service-account JSON file for Gemini/Vertex OAuth profiles.",
        ),
    ] = None,
    allow_local_base_url: Annotated[
        bool,
        typer.Option("--allow-local-base-url", help="Allow loopback HTTP provider URLs."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and print redacted setup without writing state."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print a redacted JSON result."),
    ] = False,
) -> CommandResult:
    """Capture and cache provider credentials in local credential storage."""
    try:
        normalized_provider = normalize_provider_family(provider.strip().lower())
        if mode is None:
            normalized_mode = _default_login_mode(
                normalized_provider,
                no_browser=no_browser,
                env_var=env_var,
                secret_ref=secret_ref,
                base_url=base_url,
                dry_run=dry_run,
            )
        else:
            normalized_mode = mode.strip().lower()
        if normalized_mode not in {"api-key", "oauth"}:
            raise typer.BadParameter("--mode must be api-key or oauth")
        if normalized_mode == "oauth":
            if normalized_provider == "anthropic":
                if env_var is not None or secret_ref is not None:
                    raise typer.BadParameter("--env-var and --secret-ref require --mode=api-key")
                if base_url is not None:
                    raise typer.BadParameter("--base-url is only supported by --mode=api-key")
                if project_id is not None:
                    raise typer.BadParameter("--project-id is only supported for google OAuth")
                if service_account is not None:
                    raise typer.BadParameter("--service-account is only supported for google OAuth")
                if dry_run:
                    raise typer.BadParameter("--dry-run is not supported for Anthropic OAuth login")
                _confirm_reauthentication(provider, profile_id=profile_id)
                oauth_result = anthropic_claude_cli_login(
                    profile_id=profile_id,
                )
                payload = oauth_result.capture.as_dict() | {
                    "browser_opened": oauth_result.browser_opened,
                    "setup_url": oauth_result.authorization_url,
                    "authorization_url": oauth_result.authorization_url,
                    "copy_paste_fallback": False,
                    "mode": "oauth",
                    "auth_transport": "claude-cli",
                }
                command_result = CommandResult(
                    payload=payload,
                    shape="card",
                    text="\n".join(_anthropic_oauth_login_lines(provider, oauth_result.capture)),
                )
                if json_output or oauth_result.capture.status.status != "ok":
                    emit_command_result(command_result)
                    return command_result
                _emit_auth_login_text(command_result.text or "")
                return command_result
            if env_var is not None or secret_ref is not None:
                raise typer.BadParameter("--env-var and --secret-ref require --mode=api-key")
            if base_url is not None:
                raise typer.BadParameter("--base-url is only supported by --mode=api-key")
            if dry_run:
                raise typer.BadParameter("--dry-run is not supported for browser OAuth login")
            if normalized_provider == "google":
                oauth_result = google_oauth_login(
                    profile_id=profile_id,
                    project_id=project_id,
                    service_account_path=service_account,
                )
            else:
                if service_account is not None:
                    raise typer.BadParameter("--service-account is only supported for google OAuth")
                oauth_result = browser_oauth_login(
                    provider,
                    profile_id=profile_id,
                    project_id=project_id,
                    browser_opener=_browser_opener(
                        no_browser=no_browser,
                        disclose_openai=normalized_provider == "openai",
                    ),
                    code_prompt=_code_prompt,
                )
            command_result = _oauth_login_command_result(oauth_result)
            if json_output:
                emit_command_result(command_result)
            else:
                _emit_auth_login_text(command_result.text or "")
            return command_result
        if project_id is not None:
            raise typer.BadParameter("--project-id is only supported by --mode=oauth")
        if service_account is not None:
            raise typer.BadParameter("--service-account is only supported by --mode=oauth")
        setup_url = _provider_setup_url(provider)
        browser_opened = False
        if setup_url and not no_browser and not dry_run and env_var is None and secret_ref is None:
            browser_opened = webbrowser.open(setup_url)
        if env_var is not None or secret_ref is not None:
            result: AuthCaptureResult = explicit_reference_login(
                provider,
                env_var=env_var or _default_env_var(provider),
                secret_ref=secret_ref,
                profile_id=profile_id,
                base_url=base_url,
                allow_local_base_url=allow_local_base_url,
                dry_run=dry_run,
            )
        else:
            _confirm_reauthentication(provider, profile_id=profile_id)
            credential = click.prompt(f"{provider.title()} API key", hide_input=True, err=True)
            result = capture_and_cache_login(
                provider,
                credential=credential,
                profile_id=profile_id,
                base_url=base_url,
                allow_local_base_url=allow_local_base_url,
                dry_run=dry_run,
            )
    except (
        AnthropicClaudeCliError,
        AnthropicOAuthError,
        GoogleOAuthError,
        OpenAIOAuthError,
    ) as error:
        _raise_oauth_error(str(error))
    except (ProviderURLSafetyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None

    payload = result.as_dict() | {
        "browser_opened": browser_opened,
        "setup_url": setup_url,
        "copy_paste_fallback": True,
    }
    command_result = CommandResult(
        payload=payload,
        shape="card",
        text="\n".join(_api_key_login_lines(provider, result)),
    )
    if json_output or dry_run or result.status.status != "ok":
        emit_command_result(command_result)
        return command_result
    _emit_auth_login_text(command_result.text or "")
    return command_result


@auth_app.command("logout")
@craik_command(payload_shape="kv")
def auth_logout_provider(
    provider: Annotated[
        str,
        typer.Argument(
            help=(
                "Provider family: openai, anthropic, google, or local "
                "(gemini accepted as a legacy alias)."
            ),
        ),
    ],
    profile_id: Annotated[
        str | None,
        typer.Option("--profile", help="Auth profile id to remove."),
    ] = None,
) -> CommandResult:
    """Remove a provider auth profile and cached credential."""
    from craik.cli_operator_auth import operator_identity_or_fail

    operator_identity_or_fail()
    payload = logout_provider(provider, profile_id=profile_id)
    result = CommandResult(payload=payload, shape="kv")
    emit_command_result(result)
    return result


@auth_app.command("migrate-from-env")
@craik_command(payload_shape="card_list")
def auth_migrate_from_env(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview migration by default."),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option("-y", "--yes", help="Consent to all eligible profile migrations."),
    ] = False,
) -> CommandResult:
    """Migrate env-var API-key profiles into cached credential storage."""
    consent = (lambda _prompt: True) if yes else typer.confirm
    payload = migrate_env_profiles(dry_run=dry_run, consent=consent)
    result = CommandResult(payload=payload, shape="card_list")
    emit_command_result(result)
    return result


@storage_app.command("status")
@craik_command(slash_alias="auth-storage-status", payload_shape="kv")
def auth_storage_status() -> CommandResult:
    """Show credential storage backend posture without printing secrets."""
    result = CommandResult(payload=credential_storage_status().as_dict(), shape="kv")
    emit_command_result(result)
    return result


@auth_app.command("migrate-secrets")
@craik_command(payload_shape="card")
def auth_migrate_secrets(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview migration by default."),
    ] = True,
) -> CommandResult:
    """Preview migration from file/env references into a secure backend."""
    status = credential_storage_status()
    payload = {
        "dry_run": dry_run,
        "credential_storage": status.as_dict(),
        "migrated": [],
        "requires_manual_action": status.status != "available",
        "redacted": True,
    }
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


def _default_env_var(provider: str) -> str:
    normalized = normalize_provider_family(provider.lower())
    if normalized == "anthropic":
        return "CRAIK_ANTHROPIC_API_KEY"
    if normalized == "google":
        return "CRAIK_GOOGLE_API_KEY"
    if normalized == "local":
        return "LOCAL_OPENAI_COMPATIBLE_API_KEY"
    return "CRAIK_OPENAI_API_KEY"


def _default_login_mode(
    provider: str,
    *,
    no_browser: bool,
    env_var: str | None,
    secret_ref: str | None,
    base_url: str | None,
    dry_run: bool,
) -> str:
    if env_var is not None or secret_ref is not None or base_url is not None or dry_run:
        return "api-key"
    if provider in DEFAULT_CLAUDE_CLI_PROVIDERS:
        return "oauth" if not no_browser else "api-key"
    if provider == "openai":
        if not no_browser and not bool(os.environ.get("OPENAI_API_KEY")):
            return "oauth"
        return "api-key"
    if provider in DEFAULT_OAUTH_PROVIDERS:
        return "oauth"
    return "api-key"


def _provider_setup_url(provider: str) -> str | None:
    normalized = normalize_provider_family(provider.lower())
    if normalized == "openai":
        return "https://platform.openai.com/api-keys"
    if normalized == "anthropic":
        return "https://console.anthropic.com/settings/keys"
    if normalized == "google":
        return "https://aistudio.google.com/app/apikey"
    if normalized == "local":
        return None
    return None


def _confirm_reauthentication(provider: str, *, profile_id: str | None) -> None:
    store = AuthProfileStore.from_env()
    target = profile_id or _default_profile_id(provider)
    try:
        store.get(target)
    except AuthProfileNotFoundError:
        return
    if not typer.confirm(
        f"Already logged in to {provider.title()}. Re-authenticate?",
        default=False,
    ):
        raise typer.Exit()


def _default_profile_id(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "local":
        return "chat_completions:local"
    return f"{normalized}:default"


def _credential_location_message(result: AuthCaptureResult) -> str:
    if result.profile.kind is CredentialKind.API_KEY:
        env_var = result.profile.metadata.get("env_var")
        return f"Using environment variable {env_var}." if env_var else "Using API-key profile."
    if result.profile.kind is CredentialKind.SECRET_REF:
        secret_ref = result.profile.metadata.get("secret_ref") or result.profile.metadata.get("ref")
        return f"Using secret reference {secret_ref}." if secret_ref else "Using secret reference."
    return f"Cached in {result.credential_storage.backend}."


def _api_key_login_lines(provider: str, result: AuthCaptureResult) -> list[str]:
    lines = [f"Logged into {provider.title()}. {_credential_location_message(result)}"]
    if resolve_readiness().active_model is not None:
        lines.append("Ready to chat.")
    else:
        lines.append("Set an active model with `craik model set <provider/model>`.")
    if result.warning:
        lines.append(f"Warning: {result.warning}")
    return lines


def _anthropic_oauth_login_lines(provider: str, result: AuthCaptureResult) -> list[str]:
    lines = [
        f"Logged into {provider.title()} with OAuth through the local Claude CLI. "
        "Craik will call `claude -p` instead of replaying Claude OAuth tokens."
    ]
    if resolve_readiness().active_model is not None:
        lines.append("Ready to chat.")
    else:
        lines.append("Set an active model with `craik model set <provider/model>`.")
    if result.warning:
        lines.append(f"Warning: {result.warning}")
    return lines


def _browser_opener(*, no_browser: bool, disclose_openai: bool = False) -> Callable[[str], bool]:
    def _open(url: str) -> bool:
        if no_browser:
            typer.echo(f"Open this URL to continue: {url}", err=True)
            return False
        if disclose_openai:
            _emit_openai_oauth_disclosure()
        opened = webbrowser.open(url)
        if not opened:
            typer.echo(f"Open this URL to continue: {url}", err=True)
        return opened

    return _open


def _emit_openai_oauth_disclosure() -> None:
    """Tell the operator what the OpenAI consent screen will show."""
    typer.echo(
        "\n"
        "Opening browser to OpenAI authorization.\n"
        "\n"
        '  - The consent page will identify the requesting application as "Codex".\n'
        "    Craik uses OpenAI's public Codex OAuth client for subscription billing.\n"
        "  - The resulting token will be billed against your OpenAI subscription quota.\n"
        "  - If you prefer per-token Platform API billing, cancel this flow and\n"
        "    use: craik auth login openai --mode=api-key\n"
        "\n"
        "Press Enter to continue, or Ctrl-C to cancel.",
        err=True,
    )
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        typer.echo("Aborted.", err=True)
        raise typer.Exit(2) from None


def _code_prompt(prompt: str) -> str:
    return str(click.prompt(prompt, hide_input=False, err=True))


def _oauth_login_command_result(result: OAuthLoginResult) -> CommandResult:
    provider_name = result.capture.provider.title()
    lines = [
        f"Logged into {provider_name} with OAuth. "
        f"Cached in {result.capture.credential_storage.backend}."
    ]
    if resolve_readiness().active_model is not None:
        lines.append("Ready to chat.")
    else:
        lines.append("Set an active model with `craik model set <provider/model>`.")
    return CommandResult(payload=result.as_dict(), shape="card", text="\n".join(lines))


def _emit_auth_login_text(text: str) -> None:
    typer.echo(text)


def _raise_oauth_error(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(2)
