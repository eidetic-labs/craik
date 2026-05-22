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
from craik.runtime.auth import (
    AuthProfile,
    AuthProfileNotFoundError,
    AuthProfileStore,
    AuthProfileStoreError,
    CredentialKind,
    CredentialStatus,
)
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
from craik.runtime.auth.sources import source_for_auth_profile
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)


@auth_app.command("list")
def auth_list() -> None:
    """List configured auth profiles."""
    operator_identity_or_fail()
    store = AuthProfileStore.from_env()
    payload = [_profile_payload(profile) for profile in store.list()]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@auth_app.command("add")
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
    source: Annotated[
        str | None,
        typer.Option("--source", help="Optional source hint for future credential kinds."),
    ] = None,
    credentials_path: Annotated[
        str | None,
        typer.Option("--credentials-path", help="Local CLI credentials file path."),
    ] = None,
    refresh_endpoint: Annotated[
        str | None,
        typer.Option("--refresh-endpoint", help="OAuth refresh endpoint for local CLI tokens."),
    ] = None,
    client_id: Annotated[
        str | None,
        typer.Option("--client-id", help="OAuth client id for refresh requests."),
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
) -> None:
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
    if source is not None:
        metadata["source"] = source
    if credentials_path is not None:
        metadata["credentials_path"] = str(credentials_path)
    if refresh_endpoint is not None:
        metadata["refresh_endpoint"] = refresh_endpoint
    if client_id is not None:
        metadata["client_id"] = client_id
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
    if credential_kind is CredentialKind.OAUTH_TOKEN and source != "local-cli":
        raise typer.BadParameter("--source=local-cli is required for oauth-token profiles")
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
    typer.echo(json.dumps(_profile_payload(profile), indent=2, sort_keys=True))


@auth_app.command("setup")
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
) -> None:
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
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@auth_app.command("remove")
def auth_remove(profile_id: str) -> None:
    """Remove an auth profile."""
    operator_identity_or_fail()
    AuthProfileStore.from_env().delete(profile_id)
    typer.echo(json.dumps({"removed": profile_id}, indent=2, sort_keys=True))


@auth_app.command("test")
def auth_test(profile_id: str) -> None:
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
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@auth_app.command("approve")
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
) -> None:
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
    typer.echo(json.dumps(_profile_payload(profile), indent=2, sort_keys=True))


@auth_app.command("grant")
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
) -> None:
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
    typer.echo(json.dumps(_profile_payload(profile), indent=2, sort_keys=True))


@auth_app.command("status")
def auth_status() -> None:
    """Show auth profile health and last-use status."""
    operator_identity_or_fail()
    store = AuthProfileStore.from_env()
    payload = [
        {
            "id": profile.id,
            "kind": profile.kind,
            "provider_family": profile.provider_family,
            "last_used_at": profile.last_used_at.isoformat()
            if profile.last_used_at is not None
            else None,
            "last_status": profile.last_status,
        }
        for profile in store.list()
    ]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


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
def logout(
    issuer: Annotated[
        str | None,
        typer.Option("--issuer", help="OIDC issuer URL for best-effort revocation."),
    ] = None,
    client_id: Annotated[
        str,
        typer.Option("--client-id", help="OIDC client id for best-effort revocation."),
    ] = "",
) -> None:
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
    typer.echo(json.dumps({"logged_out": True, "revoked": revoked}, indent=2, sort_keys=True))


@app.command("whoami")
def whoami() -> None:
    """Print the active operator identity."""
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(_operator_session_payload(session), indent=2, sort_keys=True))


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
        "metadata": _masked_metadata(profile.metadata),
        "created_at": profile.created_at.isoformat(),
        "last_used_at": profile.last_used_at.isoformat()
        if profile.last_used_at is not None
        else None,
        "last_status": profile.last_status,
        "authorized_operators": profile.authorized_operators,
        "authorized_operator_groups": profile.authorized_operator_groups,
        "authorization_receipt_ids": [receipt.id for receipt in profile.authorization_provenance],
    }

def _masked_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in metadata.items():
        key_lower = key.lower()
        if any(token in key_lower for token in ("token", "secret", "password")):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked

def _operator_session_payload(session: Any) -> dict[str, Any]:
    return {
        "subject": session.subject,
        "email": session.email,
        "display_name": session.display_name,
        "groups": session.groups,
        "issuer": session.issuer,
        "id_token_jti": session.id_token_jti,
        "expires_at": session.expires_at.isoformat(),
        "refresh_token_ref": session.refresh_token_ref,
    }

def _oidc_allow_loopback_http_from_env() -> bool:
    return os.environ.get("CRAIK_OIDC_ALLOW_LOOPBACK_HTTP") == "1"
