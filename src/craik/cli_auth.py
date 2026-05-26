"""Authentication profile CLI commands."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from pydantic import ValidationError

from craik.cli import app, auth_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.runtime.auth import (
    AuthProfile,
    AuthProfileNotFoundError,
    AuthProfileStore,
    AuthProfileStoreError,
    CredentialKind,
    CredentialStatus,
)
from craik.runtime.auth.commands import auth_status_result as shared_auth_status_result
from craik.runtime.auth.guided_setup import (
    DEFAULT_REF_MANAGER,
    FILE_REF_MANAGER,
    build_guided_auth_profile,
    credential_guidance,
    default_pool_for_profile,
    guided_provider_defaults,
)
from craik.runtime.auth.operator import (
    OIDCAuthenticator,
    OIDCConfig,
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)
from craik.runtime.auth.pool import CredentialPool
from craik.runtime.auth.redaction import masked_metadata
from craik.runtime.auth.sources import source_for_auth_profile
from craik.runtime.auth.visibility import active_operator_session_from_env, visible_auth_profiles
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)


@auth_app.command("list")
@craik_command(payload_shape="card_list")
def auth_list() -> CommandResult:
    """List configured auth profiles."""
    store = AuthProfileStore.from_env()
    payload = [
        _profile_payload(profile)
        for profile in visible_auth_profiles(store.list(), active_operator_session_from_env())
    ]
    result = CommandResult(payload=payload, shape="card_list")
    emit_command_result(result)
    return result


@auth_app.command("add")
@craik_command(payload_shape="card")
def auth_add(
    profile_id: str,
    kind: Annotated[
        str,
        typer.Option("--kind", help="Credential kind for this profile."),
    ],
    env_var: Annotated[
        str | None,
        typer.Option("--env-var", help="Environment variable containing an API key."),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Secret reference for secret-ref profiles."),
    ] = None,
    manager: Annotated[
        str | None,
        typer.Option("--manager", help="Secret manager for secret-ref profiles."),
    ] = None,
    secrets_root: Annotated[
        str | None,
        typer.Option("--secrets-root", help="Root directory for file secret references."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Provider base URL for this profile."),
    ] = None,
    allow_local_base_url: Annotated[
        bool,
        typer.Option("--allow-local-base-url", help="Allow loopback HTTP provider URLs."),
    ] = False,
) -> CommandResult:
    """Add or replace an auth profile."""
    operator_identity_or_fail()
    try:
        credential_kind = CredentialKind(kind)
    except ValueError:
        allowed = ", ".join(item.value for item in CredentialKind)
        message = f"unsupported credential kind; expected one of: {allowed}"
        raise typer.BadParameter(message) from None

    metadata: dict[str, Any] = {}
    if env_var is not None:
        metadata["env_var"] = env_var
    if ref is not None:
        metadata["ref"] = ref
    if manager is not None:
        metadata["manager"] = manager
    if secrets_root is not None:
        metadata["secrets_root"] = secrets_root
    if base_url is not None:
        try:
            assert_safe_provider_url(base_url, allow_local=allow_local_base_url)
        except ProviderURLSafetyError as exc:
            raise typer.BadParameter(str(exc)) from None
        metadata["base_url"] = base_url
        if allow_local_base_url:
            metadata["allow_local_base_url"] = True
    if credential_kind is CredentialKind.API_KEY and not env_var:
        raise typer.BadParameter("--env-var is required for api-key profiles")
    if credential_kind is CredentialKind.SECRET_REF:
        if not ref:
            raise typer.BadParameter("--ref is required for secret-ref profiles")
        if manager == FILE_REF_MANAGER and Path(ref).expanduser().is_absolute():
            raise typer.BadParameter("file secret refs must be relative to the secrets root")

    family = profile_id.split(":", 1)[0]
    try:
        profile = AuthProfile(
            id=profile_id,
            kind=credential_kind,
            provider_family=cast(ProviderFamily, family),
            metadata=metadata,
            created_at=datetime.now(UTC),
        )
    except ValidationError as error:
        raise typer.BadParameter(str(error)) from None

    AuthProfileStore.from_env().put(profile)
    result = CommandResult(payload=_profile_payload(profile), shape="card")
    emit_command_result(result)
    return result


@auth_app.command("setup")
@craik_command(payload_shape="card")
def auth_setup(
    provider: Annotated[
        str,
        typer.Argument(help="Provider family: openai, anthropic, gemini, or local."),
    ],
    profile_id: Annotated[
        str | None,
        typer.Option("--profile-id", help="Auth profile id to create."),
    ] = None,
    env_var: Annotated[
        str | None,
        typer.Option("--env-var", help="Environment variable containing the API key."),
    ] = None,
    secret_ref: Annotated[
        str | None,
        typer.Option("--secret-ref", help="Secret reference instead of an environment variable."),
    ] = None,
    ref_manager: Annotated[
        str,
        typer.Option("--secret-manager", help="Secret manager for --secret-ref."),
    ] = DEFAULT_REF_MANAGER,
    secrets_root: Annotated[
        str | None,
        typer.Option("--secrets-root", help="Root directory for file secret references."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Provider base URL."),
    ] = None,
    allow_local_base_url: Annotated[
        bool,
        typer.Option("--allow-local-base-url", help="Allow loopback HTTP provider URLs."),
    ] = False,
    pool: Annotated[
        bool,
        typer.Option("--pool/--no-pool", help="Create or update the default credential pool."),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and print redacted setup without writing state."),
    ] = False,
) -> CommandResult:
    """Guided setup for provider authentication profiles."""
    operator_identity_or_fail()
    try:
        resolved = guided_provider_defaults(provider)
        profile = build_guided_auth_profile(
            resolved,
            profile_id=profile_id,
            env_var=env_var,
            secret_ref=secret_ref,
            ref_manager=ref_manager,
            secrets_root=secrets_root,
            base_url=base_url,
            allow_local_base_url=allow_local_base_url,
        )
    except (ProviderURLSafetyError, ValidationError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None

    status = _source_status(profile)
    guidance = credential_guidance(profile, status)
    pool_config = default_pool_for_profile(profile) if pool else None
    if not dry_run:
        AuthProfileStore.from_env().put(profile)
        if pool_config is not None:
            CredentialPool.from_env().put(pool_config)

    payload = {
        "dry_run": dry_run,
        "provider": provider,
        "profile": _profile_payload(profile),
        "status": status.model_dump(mode="json"),
        "guidance": guidance,
        "writes": [] if dry_run else ["auth_profile", *(["credential_pool"] if pool else [])],
        "credential_pool": pool_config.model_dump(mode="json") if pool_config is not None else None,
        "redacted": True,
    }
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@auth_app.command("remove")
@craik_command(payload_shape="kv")
def auth_remove(profile_id: str) -> CommandResult:
    """Remove an auth profile."""
    operator_identity_or_fail()
    AuthProfileStore.from_env().delete(profile_id)
    result = CommandResult(payload={"removed": profile_id}, shape="kv")
    emit_command_result(result)
    return result


@auth_app.command("test")
@craik_command(payload_shape="card")
def auth_test(profile_id: str) -> CommandResult:
    """Check whether an auth profile can resolve credential material."""
    operator_identity_or_fail()
    store = AuthProfileStore.from_env()
    try:
        profile = store.get(profile_id)
    except (AuthProfileNotFoundError, AuthProfileStoreError) as error:
        raise typer.BadParameter(str(error)) from None

    status = _test_profile_status(profile)
    store.mark_used(profile.id, status.status)
    payload = {
        "id": profile.id,
        "provider_family": profile.provider_family,
        "status": status.model_dump(mode="json"),
    }
    result = CommandResult(payload=payload, shape="card")
    emit_command_result(result)
    return result


@auth_app.command("approve")
@craik_command(payload_shape="card")
def auth_approve(
    profile_id: str,
    run_id: Annotated[
        str,
        typer.Option("--run", help="Run id requesting first credential use."),
    ],
    approved_by: Annotated[
        str,
        typer.Option("--approved-by", help="Operator or approver recording approval."),
    ] = "operator:local",
) -> CommandResult:
    """Approve first live use of an auth profile for a run."""
    operator_identity_or_fail()
    try:
        profile = AuthProfileStore.from_env().approve(
            profile_id,
            run_id=run_id,
            approved_by=approved_by,
        )
    except (AuthProfileNotFoundError, AuthProfileStoreError) as error:
        raise typer.BadParameter(str(error)) from None
    result = CommandResult(payload=_profile_payload(profile), shape="card")
    emit_command_result(result)
    return result


@auth_app.command("grant")
@craik_command(payload_shape="card")
def auth_grant(
    profile_id: str,
    to_subject: Annotated[
        str | None,
        typer.Option("--to-subject", help="Operator subject authorized for this profile."),
    ] = None,
    to_group: Annotated[
        str | None,
        typer.Option("--to-group", help="Operator group authorized for this profile."),
    ] = None,
    granted_by: Annotated[
        str,
        typer.Option("--granted-by", help="Operator or approver recording the grant."),
    ] = "operator:local",
) -> CommandResult:
    """Grant an operator subject or group access to an auth profile."""
    operator_identity_or_fail()
    try:
        profile = AuthProfileStore.from_env().grant_authorization(
            profile_id,
            to_subject=to_subject,
            to_group=to_group,
            granted_by=granted_by,
        )
    except (AuthProfileNotFoundError, AuthProfileStoreError) as error:
        raise typer.BadParameter(str(error)) from None
    result = CommandResult(payload=_profile_payload(profile), shape="card")
    emit_command_result(result)
    return result


@auth_app.command("status")
@craik_command(slash_alias="auth-status", payload_shape="table")
def auth_status() -> CommandResult:
    """Show auth profile health and last-use status."""
    result = shared_auth_status_result()
    emit_command_result(result)
    return result


# craik-legacy-command: legacy OIDC device-code flow writes polling status before session exists.
@app.command("login")
def login(
    issuer: Annotated[
        str | None,
        typer.Option("--issuer", help="OIDC issuer URL. Defaults to CRAIK_OIDC_ISSUER."),
    ] = None,
    client_id: Annotated[
        str,
        typer.Option("--client-id", help="OIDC client id. Defaults to CRAIK_OIDC_CLIENT_ID."),
    ] = "",
    audience: Annotated[
        str | None,
        typer.Option("--audience", help="Optional OIDC audience value."),
    ] = None,
    max_wait_seconds: Annotated[
        int,
        typer.Option("--max-wait-seconds", help="Maximum device-code polling duration."),
    ] = 600,
) -> None:
    """Authenticate the local operator with OIDC device-code flow."""
    if issuer == "--help":
        typer.echo("Option `--issuer`: OIDC issuer URL. Defaults to CRAIK_OIDC_ISSUER.")
        typer.echo("  Must be an https:// URL outside loopback development.")
        raise typer.Exit(0)
    resolved_issuer = issuer or os.environ.get("CRAIK_OIDC_ISSUER")
    if not resolved_issuer:
        raise typer.BadParameter("--issuer or CRAIK_OIDC_ISSUER is required")
    resolved_client_id = client_id or os.environ.get("CRAIK_OIDC_CLIENT_ID", "craik-cli")
    authenticator = OIDCAuthenticator(
        OIDCConfig(
            issuer=resolved_issuer.rstrip("/"),
            client_id=resolved_client_id,
            audience=audience,
            oidc_allow_loopback_http=_oidc_allow_loopback_http_from_env(),
        )
    )
    authorization = authenticator.device_authorization()
    user_code = authorization.get("user_code")
    verification_uri = authorization.get("verification_uri") or authorization.get(
        "verification_uri_complete"
    )
    typer.echo(
        json.dumps(
            {
                "status": "authorization_pending",
                "verification_uri": verification_uri,
                "user_code": user_code,
            },
            indent=2,
            sort_keys=True,
        )
    )
    session, refresh_token = authenticator.session_and_refresh_from_token_response(
        authenticator.poll_device_token_response(
            str(authorization["device_code"]),
            interval_seconds=int(authorization.get("interval", 5) or 5),
            max_wait_seconds=max_wait_seconds,
        )
    )
    OperatorSessionStore.from_env().put(session, refresh_token=refresh_token)
    typer.echo(json.dumps(_operator_session_payload(session), indent=2, sort_keys=True))


@app.command("logout")
@craik_command(payload_shape="kv")
def logout(
    issuer: Annotated[
        str | None,
        typer.Option("--issuer", help="OIDC issuer URL for best-effort revocation."),
    ] = None,
    client_id: Annotated[
        str,
        typer.Option("--client-id", help="OIDC client id for best-effort revocation."),
    ] = "",
) -> CommandResult:
    """Clear the active operator session."""
    authenticator = None
    resolved_issuer = issuer or os.environ.get("CRAIK_OIDC_ISSUER")
    if resolved_issuer:
        authenticator = OIDCAuthenticator(
            OIDCConfig(
                issuer=resolved_issuer.rstrip("/"),
                client_id=client_id or os.environ.get("CRAIK_OIDC_CLIENT_ID", "craik-cli"),
                oidc_allow_loopback_http=_oidc_allow_loopback_http_from_env(),
            )
        )
    revoked = OperatorSessionStore.from_env().delete(authenticator=authenticator)
    result = CommandResult(payload={"logged_out": True, "revoked": revoked}, shape="kv")
    emit_command_result(result)
    return result


@app.command("whoami")
@craik_command(payload_shape="kv")
def whoami() -> CommandResult:
    """Print the active operator identity."""
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    result = CommandResult(payload=_operator_session_payload(session), shape="kv")
    emit_command_result(result)
    return result


def _source_status(profile: AuthProfile) -> CredentialStatus:
    try:
        return source_for_auth_profile(profile).status()
    except ValueError as exc:
        return CredentialStatus(status="unknown", detail=str(exc))


def _test_profile_status(profile: AuthProfile) -> CredentialStatus:
    try:
        source = source_for_auth_profile(profile)
        source.headers_for(profile.provider_family)
    except (RuntimeError, ValueError) as exc:
        return CredentialStatus(status="rejected", detail=str(exc))
    return source.status()


def _profile_payload(profile: AuthProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "kind": profile.kind,
        "provider_family": profile.provider_family,
        "metadata": masked_metadata(profile.metadata),
        "created_at": profile.created_at.isoformat(),
        "last_used_at": profile.last_used_at.isoformat()
        if profile.last_used_at is not None
        else None,
        "last_status": profile.last_status,
        "authorized_operators": profile.authorized_operators,
        "authorized_operator_groups": profile.authorized_operator_groups,
        "authorization_receipt_ids": [receipt.id for receipt in profile.authorization_provenance],
    }

def _operator_session_payload(session: Any) -> dict[str, Any]:
    return {
        "subject": session.subject,
        "email": session.email,
        "display_name": session.display_name,
        "groups": session.groups,
        "issuer": session.issuer,
        "expires_at": session.expires_at.isoformat(),
        "refresh_token_ref": session.refresh_token_ref,
    }

def _oidc_allow_loopback_http_from_env() -> bool:
    return os.environ.get("CRAIK_OIDC_ALLOW_LOOPBACK_HTTP") == "1"
