"""Doctor checks that span runtime surfaces added after setup."""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from craik.contracts.models import AgentSessionState
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.auth.store import AUTH_PROFILES_FILENAME, OWNER_ONLY_FILE_MODE
from craik.runtime.diagnostics.doctor_types import DiagnosticCheck
from craik.runtime.paths import CraikPaths
from craik.runtime.store import LocalStore


def operator_session_check(paths: CraikPaths) -> DiagnosticCheck:
    store = OperatorSessionStore(paths.home)
    if not store.path.exists():
        return DiagnosticCheck(
            name="operator_session",
            status="fail",
            summary="No active operator session is available.",
            action="Run craik login.",
        )
    try:
        session = store.get()
    except OperatorSessionNotFoundError:
        return DiagnosticCheck(
            name="operator_session",
            status="fail",
            summary="No active operator session is available.",
            action="Run craik login.",
        )
    return DiagnosticCheck(
        name="operator_session",
        status="pass",
        summary=f"Operator session is active for {session.subject}.",
    )


def model_availability_check(paths: CraikPaths, env: dict[str, str]) -> DiagnosticCheck:
    active_model = env.get("CRAIK_MODEL") or _active_model_from_settings(
        paths.config / "model-settings.json"
    )
    if active_model:
        return DiagnosticCheck(
            name="model_availability",
            status="pass",
            summary=f"Active model is configured as {active_model}.",
        )
    return DiagnosticCheck(
        name="model_availability",
        status="warning",
        summary="No active model is configured.",
        action="Run craik model set <provider/model> after configuring provider auth.",
    )


def provider_auth_check(payloads: list[dict[str, Any]]) -> DiagnosticCheck:
    if not payloads:
        return DiagnosticCheck(
            name="provider_auth",
            status="warning",
            summary="No provider auth profiles are configured.",
            action="Run craik auth login openai, anthropic, gemini, or local.",
        )
    if any(item["health"]["status"] == "ok" for item in payloads):
        return DiagnosticCheck(
            name="provider_auth",
            status="pass",
            summary="At least one provider auth profile is usable.",
        )
    return DiagnosticCheck(
        name="provider_auth",
        status="fail",
        summary="Provider auth profiles exist but none are usable.",
        action="Refresh or replace provider credentials.",
    )


def secure_credential_store_check(paths: CraikPaths) -> DiagnosticCheck:
    path = paths.home / AUTH_PROFILES_FILENAME
    if not path.exists():
        return DiagnosticCheck(
            name="secure_credential_store",
            status="pass",
            summary="No file-backed auth profile store is present.",
        )
    if os.name != "posix":
        return DiagnosticCheck(
            name="secure_credential_store",
            status="warning",
            summary="Credential file ACLs are platform-managed on this OS.",
            action="Confirm only the operator account can read auth-profiles.json.",
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode <= OWNER_ONLY_FILE_MODE:
        return DiagnosticCheck(
            name="secure_credential_store",
            status="pass",
            summary="Auth profile store is owner-only.",
        )
    return DiagnosticCheck(
        name="secure_credential_store",
        status="fail",
        summary=f"Auth profile store mode is {mode:o}; expected 600 or stricter.",
        action="Run craik doctor --fix --apply or chmod 600 auth-profiles.json.",
    )


def file_permissions_check(paths: CraikPaths) -> DiagnosticCheck:
    if os.name != "posix":
        return DiagnosticCheck(
            name="file_permissions",
            status="warning",
            summary="File permission checks are limited to POSIX platforms.",
            action="Use OS account ACLs to keep CRAIK_HOME private.",
        )
    broad = [
        path
        for path in (paths.home, paths.config, paths.state, paths.home / AUTH_PROFILES_FILENAME)
        if path.exists() and stat.S_IMODE(path.stat().st_mode) & 0o022
    ]
    if not broad:
        return DiagnosticCheck(
            name="file_permissions",
            status="pass",
            summary="Craik home paths are not group/world writable.",
        )
    return DiagnosticCheck(
        name="file_permissions",
        status="fail",
        summary=f"Writable group/world permissions found on {_join_paths(broad)}.",
        action="Run craik doctor --fix --apply for supported files, then inspect directories.",
    )


def local_endpoint_safety_check(payloads: list[dict[str, Any]]) -> DiagnosticCheck:
    unsafe = [item["id"] for item in payloads if _profile_has_unsafe_plaintext_endpoint(item)]
    if unsafe:
        return DiagnosticCheck(
            name="local_endpoint_safety",
            status="fail",
            summary=f"Plaintext non-local provider endpoints configured: {', '.join(unsafe)}.",
            action="Use HTTPS or bind local providers to localhost.",
        )
    return DiagnosticCheck(
        name="local_endpoint_safety",
        status="pass",
        summary="No plaintext non-local provider endpoints were found.",
    )


def gateway_status_check(store: LocalStore) -> DiagnosticCheck:
    states = store.list_gateway_runtime_states()
    if not states:
        return DiagnosticCheck(
            name="gateway_status",
            status="warning",
            summary="No gateway runtime state has been recorded.",
            action="Run craik gateway status after installing or starting the gateway.",
        )
    latest = sorted(states, key=lambda state: state.updated_at)[-1]
    status = "pass" if latest.status == "running" else "warning"
    return DiagnosticCheck(
        name="gateway_status",
        status=status,
        summary=f"Latest gateway state is {latest.status}.",
        action=None if status == "pass" else "Run craik gateway start when ingress is needed.",
    )


def channel_pairing_check(store: LocalStore) -> DiagnosticCheck:
    pairings = store.list_channel_identity_pairings()
    paired = [pairing for pairing in pairings if pairing.status == "paired"]
    if not pairings:
        return DiagnosticCheck(
            name="channel_pairing",
            status="warning",
            summary="No channel identity pairings are configured.",
            action="Run craik channels setup and pair external identities before live ingress.",
        )
    if paired:
        return DiagnosticCheck(
            name="channel_pairing",
            status="pass",
            summary=f"{len(paired)} channel identity pairing(s) are active.",
        )
    return DiagnosticCheck(
        name="channel_pairing",
        status="warning",
        summary="Channel identity records exist but none are paired.",
        action="Complete channel pairing before enabling live ingress.",
    )


def public_bind_security_check(store: LocalStore) -> DiagnosticCheck:
    public_configs = [
        config for config in store.list_gateway_configs() if _is_public_bind(config.bind_host)
    ]
    if not public_configs:
        return DiagnosticCheck(
            name="public_bind_security",
            status="pass",
            summary="No public gateway bind is configured.",
        )
    missing_policy = [config.id for config in public_configs if not config.policy_envelope_id]
    if missing_policy:
        return DiagnosticCheck(
            name="public_bind_security",
            status="fail",
            summary=f"Public gateway binds lack policy envelopes: {', '.join(missing_policy)}.",
            action="Attach policy envelopes or rebind gateway to 127.0.0.1.",
        )
    return DiagnosticCheck(
        name="public_bind_security",
        status="warning",
        summary="Public gateway bind is configured; verify TLS termination and network ACLs.",
        action="Use --allow-public-bind only behind explicit local network controls.",
    )


def stale_sessions_locks_check(store: LocalStore) -> DiagnosticCheck:
    stale_sessions = [
        state
        for state in store.list_agent_session_states()
        if _agent_session_stale(state, now=datetime.now(UTC))
    ]
    lock_count = len(store.list_intent_locks())
    if stale_sessions:
        return DiagnosticCheck(
            name="stale_sessions_locks",
            status="warning",
            summary=f"{len(stale_sessions)} active session(s) look stale.",
            action="Run craik session status or resume/recover the stale sessions.",
        )
    return DiagnosticCheck(
        name="stale_sessions_locks",
        status="pass",
        summary=f"No stale active sessions found; {lock_count} intent lock(s) are recorded.",
    )


def _active_model_from_settings(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = payload.get("active_model") if isinstance(payload, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _profile_has_unsafe_plaintext_endpoint(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    base_url = metadata.get("base_url")
    if not isinstance(base_url, str):
        return False
    parsed = urlparse(base_url)
    return parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}


def _agent_session_stale(state: AgentSessionState, *, now: datetime) -> bool:
    if state.status not in {"starting", "running", "idle"}:
        return False
    return state.updated_at < now - timedelta(hours=24)


def _join_paths(paths: list[Path]) -> str:
    return ", ".join(str(path) for path in paths)


def _is_public_bind(host: str) -> bool:
    try:
        return ip_address(host).is_unspecified
    except ValueError:
        return False
