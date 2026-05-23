"""Diagnostics and narrow fix planning for Craik local readiness."""

from __future__ import annotations

from typing import Any

from craik.contracts.models import GatewayConfig
from craik.runtime.auth import (
    AuthProfile,
    AuthProfileStore,
    AuthProfileStoreError,
    CredentialStatus,
)
from craik.runtime.auth.sanitization import sanitize_credential_error
from craik.runtime.auth.sources import source_for_auth_profile
from craik.runtime.diagnostics.doctor_checks import (
    channel_pairing_check,
    file_permissions_check,
    gateway_status_check,
    local_endpoint_safety_check,
    model_availability_check,
    operator_session_check,
    provider_auth_check,
    public_bind_security_check,
    secure_credential_store_check,
    stale_sessions_locks_check,
)
from craik.runtime.diagnostics.doctor_fixes import doctor_fixes
from craik.runtime.diagnostics.doctor_types import DiagnosticCheck, DiagnosticStatus
from craik.runtime.paths import CraikPaths
from craik.runtime.shell.credential_storage import FILE_BACKED_CREDENTIAL_WARNING
from craik.runtime.store import DATABASE_NAME, LocalStore, LocalStoreError


def run_doctor(
    paths: CraikPaths,
    *,
    env: dict[str, str],
    fix: bool = False,
    dry_run: bool = True,
    confirm_unsafe: bool = False,
) -> dict[str, object]:
    """Run diagnostics and optionally execute narrow, explicit fixes."""
    fixes = doctor_fixes(
        paths,
        dry_run=dry_run,
        confirm_unsafe=confirm_unsafe,
    ) if fix else []
    auth_profile_checks, auth_profile_payloads = _auth_profile_checks(paths)
    checks = [
        _home_check(paths),
        *_store_checks(paths),
        operator_session_check(paths),
        _memory_backend_check(env),
        model_availability_check(paths, env),
        *auth_profile_checks,
        provider_auth_check(auth_profile_payloads),
        secure_credential_store_check(paths),
        file_permissions_check(paths),
        local_endpoint_safety_check(auth_profile_payloads),
    ]
    store = _open_existing_store(paths)
    if store is None:
        checks.extend(
            [
                DiagnosticCheck(
                    name="gateway_config",
                    status="warning",
                    summary=(
                        "Gateway configuration is not inspectable because the local "
                        "store is missing."
                    ),
                    action="Run craik setup.",
                ),
                DiagnosticCheck(
                    name="gateway_prerequisites",
                    status="warning",
                    summary=(
                        "Gateway prerequisites cannot be checked without gateway "
                        "configuration."
                    ),
                    action="Run craik setup.",
                ),
                DiagnosticCheck(
                    name="policy",
                    status="warning",
                    summary="Policy readiness cannot be checked without gateway configuration.",
                    action="Run craik setup or persist a gateway policy envelope.",
                ),
                DiagnosticCheck(
                    name="gateway_status",
                    status="warning",
                    summary="Gateway status cannot be checked without the local store.",
                    action="Run craik setup.",
                ),
                DiagnosticCheck(
                    name="channel_pairing",
                    status="warning",
                    summary="Channel pairings cannot be checked without the local store.",
                    action="Run craik setup before enabling channel adapters.",
                ),
                DiagnosticCheck(
                    name="public_bind_security",
                    status="warning",
                    summary="Public bind posture cannot be checked without gateway config.",
                    action="Run craik setup before exposing gateway ingress.",
                ),
                DiagnosticCheck(
                    name="stale_sessions_locks",
                    status="warning",
                    summary="Session and lock state cannot be checked without the local store.",
                    action="Run craik setup.",
                ),
            ]
        )
    else:
        try:
            config = store.get_gateway_config("gateway_default")
            checks.extend(_gateway_checks(config))
            checks.append(gateway_status_check(store))
            checks.append(channel_pairing_check(store))
            checks.append(public_bind_security_check(store))
            checks.append(stale_sessions_locks_check(store))
        finally:
            store.close()
    payload: dict[str, object] = {
        "status": _overall_status(checks),
        "checks": [check.to_payload() for check in checks],
        "auth_profiles": auth_profile_payloads,
    }
    if fix:
        payload["fix"] = {
            "dry_run": dry_run,
            "unsafe_confirmed": confirm_unsafe,
            "actions": [item.to_payload() for item in fixes],
        }
    return payload


def _home_check(paths: CraikPaths) -> DiagnosticCheck:
    if paths.home.exists():
        return DiagnosticCheck(
            name="local_home",
            status="pass",
            summary=f"Craik home exists at {paths.home}.",
        )
    return DiagnosticCheck(
        name="local_home",
        status="fail",
        summary=f"Craik home does not exist at {paths.home}.",
        action="Run craik setup or craik home init.",
    )


def _store_checks(paths: CraikPaths) -> list[DiagnosticCheck]:
    database_path = paths.state / DATABASE_NAME
    if not database_path.exists():
        return [
            DiagnosticCheck(
                name="local_store",
                status="fail",
                summary=f"Local store database is missing at {database_path}.",
                action="Run craik setup.",
            )
        ]
    store = LocalStore(database_path)
    try:
        version = store.migration_version()
    except LocalStoreError as error:
        return [
            DiagnosticCheck(
                name="local_store",
                status="fail",
                summary=f"Local store could not be inspected: {error}",
                action="Re-run setup or inspect the local SQLite store.",
            )
        ]
    finally:
        store.close()
    return [
        DiagnosticCheck(
            name="local_store",
            status="pass",
            summary=f"Local store is readable at migration {version}.",
        )
    ]


def _memory_backend_check(env: dict[str, str]) -> DiagnosticCheck:
    if env.get("CRAIK_STIGMEM_URL"):
        return DiagnosticCheck(
            name="memory_backend",
            status="pass",
            summary="Stigmem URL is configured. Run connect diagnostics for live compatibility.",
        )
    return DiagnosticCheck(
        name="memory_backend",
        status="warning",
        summary="Stigmem URL is not configured; local proposal memory remains available.",
        action="Set CRAIK_STIGMEM_URL and run craik connect stigmem when shared memory is needed.",
    )


def _auth_profile_checks(paths: CraikPaths) -> tuple[list[DiagnosticCheck], list[dict[str, Any]]]:
    store = AuthProfileStore(paths.home)
    if not paths.home.exists() or not store.path.exists():
        return [
            DiagnosticCheck(
                name="auth_profiles",
                status="pass",
                summary="No auth profiles are configured.",
            )
        ], []

    try:
        profiles = store.list()
    except AuthProfileStoreError as error:
        return [
            DiagnosticCheck(
                name="auth_profiles",
                status="fail",
                summary=f"Auth profile store could not be inspected: {error}",
                action="Inspect or recreate auth-profiles.json.",
            )
        ], []

    if not profiles:
        return [
            DiagnosticCheck(
                name="auth_profiles",
                status="pass",
                summary="No auth profiles are configured.",
            )
        ], []

    payloads = [
        _auth_profile_payload(profile, _auth_profile_status(profile)) for profile in profiles
    ]
    checks = [
        DiagnosticCheck(
            name="auth_profiles",
            status=_auth_profiles_status(payloads),
            summary=f"Inspected {len(payloads)} auth profile(s).",
        )
    ]
    checks.extend(_auth_profile_check(payload) for payload in payloads)
    return checks, payloads


def _auth_profile_status(profile: AuthProfile) -> CredentialStatus:
    try:
        return source_for_auth_profile(profile).status()
    except ValueError as error:
        return CredentialStatus(status="rejected", detail=sanitize_credential_error(error))


def _auth_profile_payload(
    profile: AuthProfile,
    status: CredentialStatus,
) -> dict[str, Any]:
    backend = profile.metadata.get("credential_backend")
    backend_name = backend if isinstance(backend, str) else None
    warning = FILE_BACKED_CREDENTIAL_WARNING if backend_name == "file" else None
    return {
        "id": profile.id,
        "kind": profile.kind,
        "provider_family": profile.provider_family,
        "credential_backend": backend_name,
        "warning": warning,
        "last_used_at": profile.last_used_at.isoformat()
        if profile.last_used_at is not None
        else None,
        "last_status": profile.last_status,
        "health": status.model_dump(mode="json"),
        "metadata": {
            "base_url": profile.metadata.get("base_url")
            if isinstance(profile.metadata.get("base_url"), str)
            else None,
        },
    }


def _auth_profiles_status(payloads: list[dict[str, Any]]) -> DiagnosticStatus:
    if any(item["health"]["status"] in {"rejected", "expired"} for item in payloads):
        return "warning"
    if any(item["health"]["status"] in {"unknown", "rate_limited"} for item in payloads):
        return "warning"
    return "pass"


def _auth_profile_check(payload: dict[str, Any]) -> DiagnosticCheck:
    health = payload["health"]
    health_status = health["status"]
    status = "pass" if health_status == "ok" else "warning"
    detail = health.get("detail")
    summary = f"Auth profile {payload['id']} is {health_status}."
    if detail:
        summary = f"{summary} {detail}"
    action = None
    if health_status in {"expired", "rejected"}:
        action = "Refresh or replace the credential before running live providers."
    elif health_status == "unknown":
        action = "Complete the auth profile metadata before use."
    return DiagnosticCheck(
        name=f"auth_profile:{payload['id']}",
        status=status,
        summary=summary,
        action=action,
    )


def _gateway_checks(config: GatewayConfig | None) -> list[DiagnosticCheck]:
    if config is None:
        return [
            DiagnosticCheck(
                name="gateway_config",
                status="warning",
                summary="No gateway_default configuration is stored.",
                action="Run craik setup.",
            ),
            DiagnosticCheck(
                name="gateway_prerequisites",
                status="warning",
                summary="Gateway daemon prerequisites cannot be checked without config.",
                action="Run craik setup.",
            ),
            DiagnosticCheck(
                name="policy",
                status="warning",
                summary="Gateway policy readiness cannot be checked without config.",
                action="Persist a gateway config with a policy envelope before external ingress.",
            ),
        ]
    checks = [
        DiagnosticCheck(
            name="gateway_config",
            status="pass",
            summary=(
                f"Gateway config {config.id} is stored for "
                f"{config.bind_host}:{config.port}."
            ),
        )
    ]
    if config.mode == "daemon" and config.pid_file:
        checks.append(
            DiagnosticCheck(
                name="gateway_prerequisites",
                status="pass",
                summary="Daemon mode has a pid file configured.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="gateway_prerequisites",
                status="fail",
                summary="Daemon mode requires a pid file.",
                action="Re-run craik setup or update gateway configuration.",
            )
        )
    if config.enabled and not config.policy_envelope_id:
        checks.append(
            DiagnosticCheck(
                name="policy",
                status="warning",
                summary="Gateway is enabled without a policy envelope.",
                action="Attach a policy envelope before accepting external ingress.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="policy",
                status="pass",
                summary="Gateway policy boundary is inspectable.",
            )
        )
    return checks


def _open_existing_store(paths: CraikPaths) -> LocalStore | None:
    database_path = paths.state / DATABASE_NAME
    if not database_path.exists():
        return None
    return LocalStore(database_path)


def _overall_status(checks: list[DiagnosticCheck]) -> str:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "pass"
