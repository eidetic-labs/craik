"""Tests for the real ``GoogleAPI`` adapter (Task 4.4).

A DELTA of the API-side exemplar :mod:`test_anthropic_api`: the gate->emit
tool-loop and the receipt allow/deny reconciliation now live in the shared
``APIAdapter`` base, so this suite re-confirms the same governed behavior for the
Gemini ``generateContent`` surface -- gate via ``ctx.decide`` -> execute an
ALLOWED tool VIA the gated ``side_effects`` layer -> emit a signed
``receipt.created`` carrying ``execution="craik"`` (craik ran the tool itself),
sourced to ``google-api``. A denied tool is NEVER executed and surfaces an
``approval``-denied event with a denial receipt; a gate veto over an allow
decision emits a deny receipt (the inherited base reconciliation).

No network is hit: the recorded raw ``generateContent`` response is injected via
a fake ``request`` and the shell side-effect runs through a recording executor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craik.cli_run_support import fixture_shell_grant
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_api import GoogleAPI, SideEffectGate
from craik.runtime.backend.adapters.registry import select_adapter
from craik.runtime.backend.events import BackendEvent
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore

_RAW_FIXTURE = Path("tests/fixtures/adapters/google_generatecontent_raw.json")


def _raw_response() -> dict[str, Any]:
    return json.loads(_RAW_FIXTURE.read_text(encoding="utf-8"))


class _RecordingExecutor:
    """A ``CommandExecutor`` that records every command it is asked to run."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command_ref: str) -> dict[str, Any]:
        self.commands.append(command_ref)
        return {"command_ref": command_ref, "stdout": "audited", "exit_code": 0}


def _gate(executor: _RecordingExecutor) -> SideEffectGate:
    store = LocalStore.from_env({})
    store.initialize()
    task_id = "task_google_api_exemplar"
    policy = generate_policy_envelope(task_id=task_id, actor="runner:google-api")
    store.put_policy_envelope(policy)
    return SideEffectGate(
        store=store,
        policy=policy,
        grants=[fixture_shell_grant(task_id)],
        actor="runner:google-api",
        executor=executor,
    )


def _gate_without_grant(executor: _RecordingExecutor) -> SideEffectGate:
    """A gate whose policy grants NOTHING, so ``check_shell_grant`` vetoes.

    This produces the decision-source disagreement the inherited base
    reconciliation targets: ``ctx.decide`` says allow, but the side-effects gate
    returns a denied ``SideEffectResult`` (``allowed=False`` + a persisted denial
    receipt).
    """
    store = LocalStore.from_env({})
    store.initialize()
    task_id = "task_google_api_gate_veto"
    policy = generate_policy_envelope(task_id=task_id, actor="runner:google-api")
    store.put_policy_envelope(policy)
    return SideEffectGate(
        store=store,
        policy=policy,
        grants=[],  # no grant -> the gate vetoes despite an allow decision
        actor="runner:google-api",
        executor=executor,
    )


def _fake_request_factory() -> Any:
    def fake_request(
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> dict[str, Any]:
        # First turn returns the recorded functionCall; subsequent turns return a
        # terminal text-only candidate so the loop ends.
        if not getattr(fake_request, "called", False):
            fake_request.called = True  # type: ignore[attr-defined]
            return _raw_response()
        return {
            "modelVersion": "m",
            "candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]}}],
        }

    return fake_request


def _run_with_gate(decision: str, gate: SideEffectGate) -> list[BackendEvent]:
    adapter = GoogleAPI(side_effects=gate)
    adapter.request = _fake_request_factory()  # type: ignore[method-assign]
    ctx = RunContext(
        prompt="Run the audited shell command",
        env={},
        emit=lambda event: None,
        decide=lambda request: decision,
        require_operator_approval=False,
    )
    return list(adapter.run(ctx))


def _run(decision: str, executor: _RecordingExecutor) -> list[BackendEvent]:
    return _run_with_gate(decision, _gate(executor))


def test_supports_live_gating_is_true() -> None:
    assert GoogleAPI().supports_live_gating() is True


def test_select_adapter_returns_real_google_api() -> None:
    adapter = select_adapter("google-api", {})

    assert isinstance(adapter, GoogleAPI)
    assert adapter.vendor == "google"
    assert adapter.surface == "api"


def test_default_profile_is_google() -> None:
    assert GoogleAPI().profile.vendor == "google"


def test_auth_source_names_google_credential_profile() -> None:
    source = GoogleAPI().auth_source()
    assert "google" in source.lower()


def test_function_tools_strip_hosted_tool() -> None:
    # The ctor pre-registers the governed ``run_shell_command`` function tool.
    adapter = GoogleAPI()
    adapter.register_tool({"type": "google_search_retrieval", "name": "google_search"})

    sent = adapter.function_tools()

    names = [spec.get("name") for spec in sent]
    # The hosted google_search spec is stripped (governance); only function tools
    # survive and reach the vendor.
    assert "google_search" not in names
    assert "run_shell_command" in names
    assert all(spec.get("type") == "function" for spec in sent)


def test_allow_path_executes_via_side_effects_and_emits_craik_receipt() -> None:
    executor = _RecordingExecutor()
    events = _run("allow", executor)
    types = [event.type for event in events]

    # The tool ran VIA the gated side-effects layer (recording executor saw it).
    assert executor.commands == ["fixture-action"]

    assert "tool.used" in types
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "expected a receipt.created event for the executed tool"
    receipt = receipts[0]
    assert receipt.source == "google-api"
    assert receipt.data["execution"] == "craik"
    assert receipt.data["decision"] == "allow"
    # The receipt event carries the tool_call_id for multi-tool correlation.
    assert receipt.data["tool_call_id"] is not None

    # Every emitted event is sourced to this adapter.
    assert all(e.source == "google-api" for e in events)


def test_gate_veto_despite_allow_decision_emits_deny_receipt() -> None:
    """Inherited base reconciliation also holds for GoogleAPI.

    ``ctx.decide`` returns "allow", but the side-effects gate has no grant and
    returns a denied ``SideEffectResult`` (``allowed=False`` + a persisted denial
    receipt). The emitted receipt event MUST reflect the side-effects layer's
    actual verdict: ``decision="deny"`` matching the persisted denial, with NO
    allow receipt -- and the executor MUST never run.
    """
    executor = _RecordingExecutor()
    events = _run_with_gate("allow", _gate_without_grant(executor))

    # The gate vetoed: the real effect never executed.
    assert executor.commands == []

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "expected a receipt.created reflecting the gate verdict"
    # No allow receipt is emitted despite ctx.decide == "allow".
    assert all(r.data["decision"] == "deny" for r in receipts)
    # The deny receipt carries the persisted denial receipt id (not a stub).
    assert any(r.data["receipt_id"].startswith("receipt_") for r in receipts)


def test_assistant_text_strips_contract_envelopes() -> None:
    events = _run("allow", _RecordingExecutor())
    text_events = [e for e in events if e.type == "assistant_text"]

    assert text_events
    blob = "\n".join(str(e.as_dict()) for e in events)
    assert "craik.runner_step_result" not in blob


def test_deny_path_does_not_execute_and_emits_denied_approval() -> None:
    executor = _RecordingExecutor()
    events = _run("deny", executor)
    types = [event.type for event in events]

    # The tool was NOT executed: the recording executor never saw a command.
    assert executor.commands == []

    # A denied-approval event is emitted, carrying a deny decision.
    denied = [
        e
        for e in events
        if e.type in {"approval.resolved", "approval.denied"} and e.data.get("decision") == "deny"
    ]
    assert denied, f"expected a denied-approval event; got {types}"
    assert denied[0].source == "google-api"

    # A denial receipt is surfaced for the vetoed effect.
    denial_receipts = [
        e for e in events if e.type == "receipt.created" and e.data.get("decision") == "deny"
    ]
    assert denial_receipts, "expected a denial receipt for the vetoed tool"


def test_function_call_without_id_synthesizes_stable_tool_call_id() -> None:
    """Gemini functionCalls lack a vendor call id; a stable id is synthesized.

    The synthesized id rides through to the receipt event so multi-tool
    correlation works even on the Gemini surface.
    """
    executor = _RecordingExecutor()
    events = _run("allow", executor)

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    correlation_id = receipts[0].data["tool_call_id"]
    assert isinstance(correlation_id, str) and correlation_id
    # Synthesized from the function name + ordinal index when absent.
    assert "run_shell_command" in correlation_id
