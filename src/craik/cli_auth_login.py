"""Provider login and credential-storage CLI commands."""

from __future__ import annotations

import json
import webbrowser
from typing import Annotated

import click
import typer

from craik.cli import auth_app
from craik.runtime.auth import AuthProfileNotFoundError, AuthProfileStore
from craik.runtime.auth.login import (
    capture_and_cache_login,
    explicit_reference_login,
    logout_provider,
    migrate_env_profiles,
)
from craik.runtime.providers.provider_url_safety import ProviderURLSafetyError
from craik.runtime.shell.credential_storage import credential_storage_status

storage_app = typer.Typer(help="Inspect and migrate credential storage posture.")
auth_app.add_typer(storage_app, name="storage")


@auth_app.command("login")
def auth_login_provider(
    provider: Annotated[
        str,
        typer.Argument(help="Provider family: openai, anthropic, gemini, or local."),
    ] = "openai",
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="Print provider setup URL instead of opening a browser."),
    ] = False,
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
) -> None:
    """Capture and cache provider credentials in local credential storage."""
    try:
        setup_url = _provider_setup_url(provider)
        browser_opened = False
        if setup_url and not no_browser and not dry_run and env_var is None and secret_ref is None:
            browser_opened = webbrowser.open(setup_url)
        if env_var is not None or secret_ref is not None:
            result = explicit_reference_login(
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
    except (ProviderURLSafetyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None

    payload = result.as_dict() | {
        "browser_opened": browser_opened,
        "setup_url": setup_url,
        "copy_paste_fallback": True,
    }
    if json_output or dry_run or result.status.status != "ok":
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    provider_name = provider.title()
    typer.echo(
        f"Logged into {provider_name}. Cached in "
        f"{result.credential_storage.backend}. Ready to chat."
    )
    if result.warning:
        typer.echo(f"Warning: {result.warning}")


@auth_app.command("logout")
def auth_logout_provider(
    provider: Annotated[
        str,
        typer.Argument(help="Provider family: openai, anthropic, gemini, or local."),
    ],
    profile_id: Annotated[
        str | None,
        typer.Option("--profile", help="Auth profile id to remove."),
    ] = None,
) -> None:
    """Remove a provider auth profile and cached credential."""
    from craik.cli_operator_auth import operator_identity_or_fail

    operator_identity_or_fail()
    payload = logout_provider(provider, profile_id=profile_id)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@auth_app.command("migrate-from-env")
def auth_migrate_from_env(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview migration by default."),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option("-y", "--yes", help="Consent to all eligible profile migrations."),
    ] = False,
) -> None:
    """Migrate env-var API-key profiles into cached credential storage."""
    consent = (lambda _prompt: True) if yes else typer.confirm
    payload = migrate_env_profiles(dry_run=dry_run, consent=consent)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@storage_app.command("status")
def auth_storage_status() -> None:
    """Show credential storage backend posture without printing secrets."""
    typer.echo(json.dumps(credential_storage_status().as_dict(), indent=2, sort_keys=True))


@auth_app.command("migrate-secrets")
def auth_migrate_secrets(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview migration by default."),
    ] = True,
) -> None:
    """Preview migration from file/env references into a secure backend."""
    status = credential_storage_status()
    payload = {
        "dry_run": dry_run,
        "credential_storage": status.as_dict(),
        "migrated": [],
        "requires_manual_action": status.status != "available",
        "redacted": True,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _default_env_var(provider: str) -> str:
    normalized = provider.lower()
    if normalized == "anthropic":
        return "CRAIK_ANTHROPIC_API_KEY"
    if normalized == "gemini":
        return "CRAIK_GEMINI_API_KEY"
    if normalized == "local":
        return "LOCAL_OPENAI_COMPATIBLE_API_KEY"
    return "CRAIK_OPENAI_API_KEY"


def _provider_setup_url(provider: str) -> str | None:
    normalized = provider.lower()
    if normalized == "openai":
        return "https://platform.openai.com/api-keys"
    if normalized == "anthropic":
        return "https://console.anthropic.com/settings/keys"
    if normalized == "gemini":
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
