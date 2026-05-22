"""Provider login and credential-storage CLI commands."""

from __future__ import annotations

import json
import webbrowser
from typing import Annotated

import typer
from pydantic import ValidationError

from craik.cli import auth_app
from craik.cli_auth import _profile_payload, _source_status
from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.guided_setup import (
    DEFAULT_REF_MANAGER,
    build_guided_auth_profile,
    default_pool_for_profile,
    guided_provider_defaults,
)
from craik.runtime.auth.pool import CredentialPool
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
) -> None:
    """Browser-assisted provider login with secure copy/paste fallback."""
    try:
        resolved = guided_provider_defaults(provider)
        default_env_var = env_var or _default_env_var(provider)
        profile = build_guided_auth_profile(
            resolved,
            profile_id=profile_id,
            env_var=default_env_var,
            secret_ref=secret_ref,
            ref_manager=DEFAULT_REF_MANAGER,
            secrets_root=None,
            base_url=base_url,
            allow_local_base_url=allow_local_base_url,
        )
    except (ProviderURLSafetyError, ValidationError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None

    setup_url = _provider_setup_url(provider)
    browser_opened = False
    if setup_url and not no_browser and not dry_run:
        browser_opened = webbrowser.open(setup_url)
    status = _source_status(profile)
    if not dry_run:
        AuthProfileStore.from_env().put(profile)
        CredentialPool.from_env().put(default_pool_for_profile(profile))
    payload = {
        "provider": provider,
        "profile": _profile_payload(profile),
        "status": status.model_dump(mode="json"),
        "browser_opened": browser_opened,
        "setup_url": setup_url,
        "copy_paste_fallback": True,
        "credential_storage": credential_storage_status().as_dict(),
        "dry_run": dry_run,
        "redacted": True,
    }
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
