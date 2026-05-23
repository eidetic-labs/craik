"""Authenticated local dashboard surface."""

from __future__ import annotations

import html
import json
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.visibility import visible_auth_profiles
from craik.runtime.dashboard.auth import (
    active_operator_session,
    dashboard_auth_failure_payload,
    dashboard_authorized,
    has_operator_session,
)
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.reviewing.approvals import approval_queue_payload
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command, slash_command_is_mutating
from craik.runtime.store import DATABASE_NAME, LocalStore

LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}


class DashboardConfigError(RuntimeError):
    """Raised when a dashboard configuration would be unsafe or unusable."""


@dataclass(frozen=True)
class DashboardConfig:
    """Dashboard server configuration."""

    host: str = "127.0.0.1"
    port: int = 8787
    auth_token: str | None = None
    allow_unsafe_bind: bool = False


@dataclass(frozen=True)
class DashboardResponse:
    """Pure dashboard route response used by the HTTP server and tests."""

    status: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class DashboardPage:
    """Rendered dashboard page content."""

    title: str
    items: list[str]


def issue_dashboard_token() -> str:
    """Return an unguessable dashboard bearer token."""
    return secrets.token_urlsafe(32)


def validate_dashboard_config(
    config: DashboardConfig,
    *,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Validate bind and authentication posture, returning operator warnings."""
    warnings: list[str] = []
    if not _is_local_bind(config.host):
        if not config.allow_unsafe_bind:
            raise DashboardConfigError(
                "non-local dashboard bind requires --allow-unsafe-dashboard-bind"
            )
        warnings.append(
            "Dashboard is bound outside localhost; place it behind local-only access controls."
        )
    if config.auth_token is None and not has_operator_session(env):
        raise DashboardConfigError(
            "dashboard requires an active operator session or --auth-token"
        )
    return warnings


def dashboard_url(config: DashboardConfig) -> str:
    """Return the operator-facing dashboard URL."""
    return f"http://{config.host}:{config.port}/"


def run_dashboard_server(
    config: DashboardConfig,
    *,
    env: dict[str, str] | None = None,
) -> None:
    """Run the local dashboard server until interrupted."""
    validate_dashboard_config(config, env=env)
    server = ThreadingHTTPServer((config.host, config.port), _handler(config, env))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def handle_dashboard_request(
    method: str,
    path: str,
    headers: Any,
    body: bytes,
    config: DashboardConfig,
    *,
    env: dict[str, str] | None = None,
) -> DashboardResponse:
    """Handle one dashboard request without binding a socket."""
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    if not dashboard_authorized(headers, query, config.auth_token, env=env):
        return _json_response(
            HTTPStatus.UNAUTHORIZED,
            dashboard_auth_failure_payload(headers, query, config.auth_token, env=env),
        )
    if method == "GET":
        if parsed.path == "/api/approvals":
            return _api_approvals(env)
        return _get(parsed.path, config=config, env=env)
    if method == "POST" and parsed.path == "/api/actions":
        if not _origin_allowed(headers, config):
            return _json_response(HTTPStatus.FORBIDDEN, {"error": "dashboard origin not allowed"})
        return _post_action(body, env=env)
    return _json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})


def dashboard_preview_payload(
    config: DashboardConfig,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Return non-secret dashboard launch metadata for dry-run output."""
    warnings = validate_dashboard_config(config, env=env)
    if config.auth_token is None:
        warnings.append(
            "Operator-session dashboard auth requires X-Craik-Operator-Session bound "
            "to the active session."
        )
    return {
        "url": dashboard_url(config),
        "host": config.host,
        "port": config.port,
        "auth": "token" if config.auth_token else "operator-session",
        "warnings": warnings,
    }


def _get(path: str, *, config: DashboardConfig, env: dict[str, str] | None) -> DashboardResponse:
    snapshot = _dashboard_snapshot(env)
    if path in {"", "/"}:
        return _html_response("Craik Dashboard", _index_html(snapshot))
    if path == "/api/status":
        return _json_response(HTTPStatus.OK, snapshot)
    page = _page_for_path(path, snapshot)
    if page is None:
        return _json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
    return _html_response(page.title, _page_html(page.items, config))


def _post_action(body: bytes, *, env: dict[str, str] | None) -> DashboardResponse:
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
    command = payload.get("command")
    if not isinstance(command, str) or not command.startswith("/"):
        return _json_response(HTTPStatus.BAD_REQUEST, {"error": "command must be a slash command"})
    if slash_command_is_mutating(command):
        return _json_response(
            HTTPStatus.FORBIDDEN,
            {"error": "mutating slash commands are not allowed from the dashboard"},
        )
    result = dispatch_slash_command(command, env=env)
    return _json_response(
        HTTPStatus.OK,
        {
            "command": _safe(command),
            "exit_code": result.exit_code,
            "text": _safe(result.text),
            "receipt": "not emitted for read-only dashboard action",
        },
    )


def _dashboard_snapshot(env: dict[str, str] | None) -> dict[str, object]:
    readiness = resolve_readiness(env).as_dict()
    paths = resolve_craik_paths(env)
    counts: dict[str, int] = {
        "sessions": 0,
        "runs": 0,
        "handoffs": 0,
        "receipts": 0,
        "approvals": 0,
        "gateway_states": 0,
        "skill_proposals": 0,
    }
    providers: list[dict[str, str | None]] = []
    gateway_logs = str(paths.logs / "gateway.log")
    if (paths.state / DATABASE_NAME).exists():
        store = LocalStore.from_paths(paths)
        try:
            store.initialize()
            counts.update(
                {
                    "sessions": _count(store, "list_agent_session_states"),
                    "runs": _count(store, "list_task_runs"),
                    "handoffs": _count(store, "list_handoffs"),
                    "receipts": _count(store, "list_receipts")
                    + _count(store, "list_plugin_receipts"),
                    "approvals": len(
                        [
                            delegation
                            for delegation in store.list_human_delegations()
                            if delegation.kind == "approval" and delegation.status == "open"
                        ]
                    ),
                    "gateway_states": _count(store, "list_gateway_runtime_states"),
                    "skill_proposals": _count(store, "list_distilled_instruction_proposals"),
                }
            )
        finally:
            store.close()
    try:
        visible = visible_auth_profiles(
            AuthProfileStore.from_env(env).list(),
            active_operator_session(env),
        )
        providers = [
            {
                "id": _safe(profile.id),
                "family": _safe(profile.provider_family),
                "status": _safe(profile.last_status or "unknown"),
            }
            for profile in visible
        ]
    except Exception:
        providers = []
    return _redacted(
        {
            "readiness": readiness,
            "counts": counts,
            "providers": providers,
            "gateway_logs": gateway_logs,
            "model_picker": readiness.get("active_model") or "not selected",
            "redacted": True,
        }
    )


def _page_for_path(path: str, snapshot: dict[str, object]) -> DashboardPage | None:
    counts = snapshot["counts"]
    if not isinstance(counts, dict):
        counts = {}
    pages: dict[str, tuple[str, list[str]]] = {
        "/status": ("Status", _status_items(snapshot)),
        "/config": ("Config", [f"home: {snapshot['readiness']}"]),
        "/providers": ("Providers", _provider_items(snapshot)),
        "/auth": ("Auth", ["operator session or dashboard token required"]),
        "/sessions": ("Sessions", [f"sessions: {counts.get('sessions', 0)}"]),
        "/runs": ("Runs", [f"runs: {counts.get('runs', 0)}"]),
        "/handoffs": ("Handoffs", [f"handoffs: {counts.get('handoffs', 0)}"]),
        "/receipts": ("Receipts", [f"receipts: {counts.get('receipts', 0)}"]),
        "/approvals": ("Approvals", _approval_items(snapshot)),
        "/gateway/logs": ("Gateway Logs", [f"log: {snapshot['gateway_logs']}"]),
        "/skills": ("Skill Proposals", [f"proposals: {counts.get('skill_proposals', 0)}"]),
        "/models": ("Model Picker", [f"active: {snapshot['model_picker']}"]),
    }
    page = pages.get(path)
    if page is None:
        return None
    return DashboardPage(title=page[0], items=page[1])


def _index_html(snapshot: dict[str, object]) -> str:
    links = [
        "/status",
        "/config",
        "/providers",
        "/auth",
        "/sessions",
        "/runs",
        "/handoffs",
        "/receipts",
        "/approvals",
        "/gateway/logs",
        "/skills",
        "/models",
    ]
    items = "".join(f'<li><a href="{path}">{html.escape(path)}</a></li>' for path in links)
    status = _safe(str(snapshot["readiness"]))
    return f"<p>{html.escape(status)}</p><nav><ul>{items}</ul></nav>"


def _page_html(items: list[str], config: DashboardConfig) -> str:
    rendered = "".join(f"<li>{html.escape(_safe(item))}</li>" for item in items)
    bind = "unsafe-public" if not _is_local_bind(config.host) else "local-only"
    return f"<p>Bind: {bind}</p><ul>{rendered}</ul>"


def _status_items(snapshot: dict[str, object]) -> list[str]:
    readiness = snapshot["readiness"]
    if isinstance(readiness, dict):
        return [
            f"state: {readiness.get('state', 'unknown')}",
            f"active model: {readiness.get('active_model') or 'not selected'}",
            f"missing: {', '.join(readiness.get('missing', []))}",
        ]
    return ["state: unknown"]


def _provider_items(snapshot: dict[str, object]) -> list[str]:
    providers = snapshot["providers"]
    if not isinstance(providers, list) or not providers:
        return ["providers: none configured or visible"]
    return [str(provider) for provider in providers]


def _approval_items(snapshot: dict[str, object]) -> list[str]:
    counts = snapshot["counts"]
    count = counts.get("approvals", 0) if isinstance(counts, dict) else 0
    return [
        f"open approvals: {count}",
        "actions: craik approvals show <id>",
        "approve: craik approvals approve <id> --reason <reason>",
        "deny: craik approvals deny <id> --reason <reason>",
    ]


def _api_approvals(env: dict[str, str] | None) -> DashboardResponse:
    paths = resolve_craik_paths(env)
    if not (paths.state / DATABASE_NAME).exists():
        return _json_response(HTTPStatus.OK, {"count": 0, "approvals": []})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        payload = approval_queue_payload(store)
    finally:
        store.close()
    return _json_response(HTTPStatus.OK, payload)


def _handler(
    config: DashboardConfig,
    env: dict[str, str] | None,
) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        server_version = "CraikDashboard/0.11"

        def do_GET(self) -> None:  # noqa: N802
            self._write(
                handle_dashboard_request("GET", self.path, self.headers, b"", config, env=env)
            )

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self._write(
                handle_dashboard_request("POST", self.path, self.headers, body, config, env=env)
            )

        def log_message(self, _format: str, *args: object) -> None:
            return

        def _write(self, response: DashboardResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

    return DashboardRequestHandler


def _origin_allowed(headers: Any, config: DashboardConfig) -> bool:
    origin = headers.get("Origin")
    if not origin:
        return True
    return origin.rstrip("/") in _allowed_origins(config)


def _allowed_origins(config: DashboardConfig) -> set[str]:
    origins = {
        f"http://127.0.0.1:{config.port}",
        f"http://localhost:{config.port}",
    }
    if config.host == "::1":
        origins.add(f"http://[::1]:{config.port}")
    else:
        origins.add(f"http://{config.host}:{config.port}")
    return origins


def _is_local_bind(host: str) -> bool:
    return host in LOCAL_DASHBOARD_HOSTS


def _count(store: LocalStore, method_name: str) -> int:
    method = getattr(store, method_name)
    return len(list(method()))


def _html_response(title: str, body: str) -> DashboardResponse:
    html_body = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(_safe(title))}</title></head><body>"
        f"<h1>{html.escape(_safe(title))}</h1>{body}</body></html>"
    ).encode()
    return DashboardResponse(HTTPStatus.OK, "text/html; charset=utf-8", html_body)


def _json_response(status: int | HTTPStatus, payload: dict[str, object]) -> DashboardResponse:
    body = json.dumps(_redacted(payload), indent=2, sort_keys=True).encode("utf-8")
    return DashboardResponse(int(status), "application/json", body)


def _redacted(payload: dict[str, object]) -> dict[str, object]:
    value = redact(payload).value
    if not isinstance(value, dict):
        return {"value": _safe(str(value))}
    return value


def _safe(value: str) -> str:
    return sanitize_runtime_text(str(redact(value).value))
