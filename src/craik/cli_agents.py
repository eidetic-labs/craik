"""Persistent agent lifecycle commands for the Craik CLI."""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_run_support import provider_run_payload
from craik.contracts.models import AgentSessionState
from craik.runtime.agents import (
    AgentPromptResult,
    AgentSessionLifecycleError,
    AgentSessionRecoveryError,
    agent_session_id,
    execute_agent_prompt,
    get_agent_session_status,
    mark_agent_session_failure_by_id,
    recover_agent_session_by_id,
    restart_agent_session,
    start_agent_session,
    stop_agent_session,
)
from craik.runtime.agents.session_naming import SessionNameError, validate_session_name
from craik.runtime.auth.operator import OperatorSessionStore
from craik.runtime.store import LocalStore

agent_app = typer.Typer(help="Launch and manage persistent Craik agent sessions.")


@agent_app.command("launch")
def agent_launch(
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Explicit persistent agent session id."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Project scope for the persistent agent."),
    ] = None,
    provider_id: Annotated[
        str,
        typer.Option("--provider-id", help="Provider runtime id for the session."),
    ] = "provider_openai",
    model_id: Annotated[
        str | None,
        typer.Option("--model-id", help="Provider model id requested for the session."),
    ] = None,
    auth_profile_id: Annotated[
        str | None,
        typer.Option("--auth-profile-id", help="Credential profile id used by the session."),
    ] = None,
    policy_envelope_id: Annotated[
        str | None,
        typer.Option("--policy-envelope-id", help="Policy envelope governing the session."),
    ] = None,
    endpoint_url: Annotated[
        str | None,
        typer.Option(
            "--endpoint-url",
            help="Local endpoint URL when a foreground loop exposes one.",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Operator-visible session display name."),
    ] = None,
) -> None:
    """Launch a foreground persistent agent session control record."""
    operator_subject = operator_identity_or_fail()
    operator = OperatorSessionStore.from_env().get()
    store = LocalStore.from_env()
    try:
        store.initialize()
        resolved_session_id = session_id or agent_session_id(
            project_id=project_id,
            provider_id=provider_id,
        )
        state = start_agent_session(
            store,
            session_id=resolved_session_id,
            project_id=project_id,
            operator_subject=operator_subject,
            operator_issuer=operator.issuer,
            provider_id=provider_id,
            model_id=model_id,
            auth_profile_id=auth_profile_id,
            policy_envelope_id=policy_envelope_id,
            endpoint_url=endpoint_url,
            display_name=_resolved_agent_name(name),
            mode="foreground",
            status="running",
        )
        payload = {
            "launched": True,
            "boundary": _boundary_payload(),
            "session": _session_payload(state),
        }
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("rename")
def agent_rename(
    session_id: Annotated[str, typer.Argument(help="Agent session id.")],
    name: Annotated[str, typer.Argument(help="New operator-visible display name.")],
) -> None:
    """Rename a persistent agent session."""
    operator_identity_or_fail()
    try:
        display_name = validate_session_name(name)
    except SessionNameError as error:
        raise typer.BadParameter(str(error)) from None
    store = LocalStore.from_env()
    try:
        store.initialize()
        state = get_agent_session_status(store, session_id)
        updated = AgentSessionState.model_validate(
            {**state.model_dump(mode="json", by_alias=True), "display_name": display_name}
        )
        store.put_agent_session_state(updated)
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps({"renamed": True, "session": _session_payload(updated)}, indent=2))


@agent_app.command("list")
def agent_list() -> None:
    """List persisted persistent agent sessions."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        sessions = sorted(
            store.list_agent_session_states(),
            key=lambda state: state.updated_at,
            reverse=True,
        )
        payload = [_session_payload(session) for session in sessions]
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("status")
def agent_status(session_id: Annotated[str, typer.Argument(help="Agent session id.")]) -> None:
    """Inspect one persistent agent session."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        read_result = store.get_agent_session_state_with_verification(session_id)
        if read_result is None:
            raise AgentSessionLifecycleError(f"unknown agent session: {session_id}")
        if read_result.hmac_status == "tampered":
            state = read_result.state
            hmac_status = "tampered"
        else:
            state = get_agent_session_status(store, session_id)
            refreshed = store.get_agent_session_state_with_verification(session_id)
            hmac_status = (
                refreshed.hmac_status
                if refreshed is not None
                else read_result.hmac_status
            )
        payload = {"session": _session_payload(state), "hmac_status": hmac_status}
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("stop")
def agent_stop(
    session_id: Annotated[str, typer.Argument(help="Agent session id.")],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Operator-visible lifecycle reason."),
    ] = "stopped by operator",
) -> None:
    """Stop an active persistent agent session."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        state = stop_agent_session(
            store,
            session_id,
            supervision_note=reason,
        )
        payload = {"stopped": True, "session": _session_payload(state)}
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("restart")
def agent_restart(
    session_id: Annotated[str, typer.Argument(help="Agent session id.")],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Operator-visible lifecycle reason."),
    ] = "restarted by operator",
    endpoint_url: Annotated[
        str | None,
        typer.Option("--endpoint-url", help="Replacement endpoint URL when one is exposed."),
    ] = None,
) -> None:
    """Restart a stopped or failed persistent agent session."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        state = restart_agent_session(
            store,
            session_id,
            supervision_note=reason,
            endpoint_url=endpoint_url,
        )
        payload = {"restarted": True, "session": _session_payload(state)}
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("prompt")
def agent_prompt(
    session_id: Annotated[str, typer.Argument(help="Agent session id.")],
    prompt: Annotated[str, typer.Argument(help="Prompt text, or /exit to stop the loop.")],
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", min=1, help="Maximum provider loop iterations."),
    ] = 5,
    allow_fixture_action: Annotated[
        bool,
        typer.Option(
            "--allow-fixture-action/--no-allow-fixture-action",
            help="Grant the deterministic fixture shell action used by provider tests.",
        ),
    ] = True,
    provider_token_budget: Annotated[
        int | None,
        typer.Option("--provider-token-budget", min=1, help="Optional provider token budget."),
    ] = None,
) -> None:
    """Send one provider-backed prompt to an active persistent agent session."""
    operator_subject = operator_identity_or_fail()
    operator = OperatorSessionStore.from_env().get()
    store = LocalStore.from_env()
    try:
        store.initialize()
        result = execute_agent_prompt(
            store,
            session_id=session_id,
            operator_subject=operator_subject,
            operator_issuer=operator.issuer,
            prompt=prompt,
            allow_fixture_action=allow_fixture_action,
            max_iterations=max_iterations,
            provider_token_budget=provider_token_budget,
        )
        payload = _agent_prompt_payload(result)
    except AgentSessionLifecycleError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@agent_app.command("recover")
def agent_recover(
    session_id: Annotated[str, typer.Argument(help="Agent session id.")],
    reason: Annotated[
        str | None,
        typer.Option(
            "--reason",
            help=(
                "Failure reason: auth_expired, provider_unavailable, "
                "sandbox_failed, stale_endpoint."
            ),
        ),
    ] = None,
    action: Annotated[
        str | None,
        typer.Option("--action", help="Recovery action: reconnect or resume."),
    ] = None,
    detail: Annotated[
        str | None,
        typer.Option("--detail", help="Redacted operator recovery detail."),
    ] = None,
) -> None:
    """Mark or perform a persistent agent recovery transition."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        if action is not None:
            state = recover_agent_session_by_id(
                store,
                session_id,
                action=_recovery_action(action),
                supervision_note=f"Persistent agent recovery action: {action}.",
            )
        else:
            if reason is None:
                raise typer.BadParameter("reason is required when action is omitted")
            state = mark_agent_session_failure_by_id(
                store,
                session_id,
                reason=_recovery_reason(reason),
                detail=detail,
                source="operator",
            )
        payload = {"recovered": True, "session": _session_payload(state)}
    except (AgentSessionLifecycleError, AgentSessionRecoveryError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _session_payload(state: AgentSessionState) -> dict[str, Any]:
    payload = state.model_dump(mode="json", by_alias=True)
    payload["runtime_boundary"] = "persistent_agent"
    return payload


def _resolved_agent_name(name: str | None) -> str | None:
    raw = name or os.environ.get("CRAIK_SESSION_NAME")
    if raw is None:
        return None
    try:
        return validate_session_name(raw)
    except SessionNameError as error:
        raise typer.BadParameter(str(error)) from None


def _boundary_payload() -> dict[str, str]:
    return {
        "persistent_agent": "craik agent launch/status/prompt/stop/restart",
        "one_shot_run": "craik run execute",
    }


def _agent_prompt_payload(result: AgentPromptResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "craik.agent_prompt_execution",
        "version": "0.1.0",
        "exit_behavior": result.exit_behavior,
        "session": _session_payload(result.session),
        "events": [
            event.model_dump(mode="json", by_alias=True)
            for event in result.events
        ],
    }
    if result.task_id is not None:
        payload["task_id"] = result.task_id
    if result.run_result is not None:
        payload["run"] = provider_run_payload(result.run_result)
    return payload


def _recovery_reason(value: str) -> Any:
    allowed = {"auth_expired", "provider_unavailable", "sandbox_failed", "stale_endpoint"}
    if value not in allowed:
        raise typer.BadParameter(
            "reason must be auth_expired, provider_unavailable, sandbox_failed, or stale_endpoint"
        )
    return value


def _recovery_action(value: str) -> Any:
    if value not in {"reconnect", "resume"}:
        raise typer.BadParameter("action must be reconnect or resume")
    return value
