"""Tests for the real ``OpenAIAPI`` adapter (Task 4.5).

A DELTA of the API-side exemplars :mod:`test_anthropic_api` / :mod:`test_google_api`:
the gate->emit tool-loop and the receipt allow/deny reconciliation now live in
the shared ``APIAdapter`` base, so this suite re-confirms the same governed
behavior for the OpenAI Responses-API surface -- gate via ``ctx.decide`` ->
execute an ALLOWED tool VIA the gated ``side_effects`` layer -> emit a signed
``receipt.created`` carrying ``execution="craik"`` (craik ran the tool itself),
sourced to ``openai-api``. A denied tool is NEVER executed and surfaces an
``approval``-denied event with a denial receipt; a gate veto over an allow
decision emits a deny receipt (the inherited base reconciliation).

The OpenAI surface has a primary Responses path and a Chat Completions fallback;
both are exercised here. No network is hit: the recorded raw response is injected
via a fake ``request`` and the shell side-effect runs through a recording
executor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craik.cli_run_support import fixture_shell_grant
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.openai_api import OpenAIAPI, SideEffectGate
from craik.runtime.backend.adapters.registry import select_adapter
from craik.runtime.backend.events import BackendEvent
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore

_RAW_FIXTURE = Path("tests/fixtures/adapters/openai_responses_raw.json")


def _raw_response() -> dict[str, Any]:
    return json.loads(_RAW_FIXTURE.read_text(encoding="utf-8"))


def _raw_chat_completions_response() -> dict[str, Any]:
    """A Chat Completions response carrying the same governed tool call."""
    return {
        "id": "chatcmpl_openai_api_exemplar",
        "model": "gpt-5.4",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "Running the requested shell command now. craik.runner_step_result",
                    "tool_calls": [
                        {
                            "id": "call_chat_openai_api_shell",
                            "type": "function",
                            "function": {
                                "name": "run_shell_command",
                                "arguments": '{"command": "fixture-action"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 17, "total_tokens": 59},
    }


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
    task_id = "task_openai_api_exemplar"
    policy = generate_policy_envelope(task_id=task_id, actor="runner:openai-api")
    store.put_policy_envelope(policy)
    return SideEffectGate(
        store=store,
        policy=policy,
        grants=[fixture_shell_grant(task_id)],
        actor="runner:openai-api",
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
    task_id = "task_openai_api_gate_veto"
    policy = generate_policy_envelope(task_id=task_id, actor="runner:openai-api")
    store.put_policy_envelope(policy)
    return SideEffectGate(
        store=store,
        policy=policy,
        grants=[],  # no grant -> the gate vetoes despite an allow decision
        actor="runner:openai-api",
        executor=executor,
    )


def _fake_request_factory(first: dict[str, Any], terminal: dict[str, Any]) -> Any:
    def fake_request(
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> dict[str, Any]:
        # First turn returns the recorded tool call; subsequent turns return a
        # terminal text-only response so the loop ends.
        if not getattr(fake_request, "called", False):
            fake_request.called = True  # type: ignore[attr-defined]
            return first
        return terminal

    return fake_request


def _responses_terminal() -> dict[str, Any]:
    return {
        "id": "resp_done",
        "model": "gpt-5.4",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            }
        ],
    }


def _chat_completions_terminal() -> dict[str, Any]:
    return {
        "id": "chatcmpl_done",
        "model": "gpt-5.4",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "done"},
            }
        ],
    }


def _run_with_gate(
    decision: str,
    gate: SideEffectGate,
    *,
    use_chat_completions: bool = False,
) -> list[BackendEvent]:
    adapter = OpenAIAPI(side_effects=gate, use_chat_completions=use_chat_completions)
    if use_chat_completions:
        adapter.request = _fake_request_factory(  # type: ignore[method-assign]
            _raw_chat_completions_response(), _chat_completions_terminal()
        )
    else:
        adapter.request = _fake_request_factory(  # type: ignore[method-assign]
            _raw_response(), _responses_terminal()
        )
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
    assert OpenAIAPI().supports_live_gating() is True


def test_select_adapter_returns_real_openai_api() -> None:
    adapter = select_adapter("openai-api", {})

    assert isinstance(adapter, OpenAIAPI)
    assert adapter.vendor == "openai"
    assert adapter.surface == "api"


def test_default_profile_is_openai() -> None:
    assert OpenAIAPI().profile.vendor == "openai"


def test_auth_source_names_openai_credential_profile() -> None:
    source = OpenAIAPI().auth_source()
    assert "openai" in source.lower()


def test_function_tools_strip_hosted_tool() -> None:
    # The ctor pre-registers the governed ``run_shell_command`` function tool.
    adapter = OpenAIAPI()
    adapter.register_tool({"type": "web_search", "name": "web_search"})
    adapter.register_tool({"type": "code_interpreter", "name": "code_interpreter"})

    sent = adapter.function_tools()

    names = [spec.get("name") for spec in sent]
    # The hosted web_search / code_interpreter specs are stripped (governance);
    # only function tools survive and reach the vendor.
    assert "web_search" not in names
    assert "code_interpreter" not in names
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
    assert receipt.source == "openai-api"
    assert receipt.data["execution"] == "craik"
    assert receipt.data["decision"] == "allow"
    # The receipt event carries the tool_call_id for multi-tool correlation.
    assert receipt.data["tool_call_id"] is not None

    # Every emitted event is sourced to this adapter.
    assert all(e.source == "openai-api" for e in events)


def test_responses_tool_call_uses_vendor_call_id() -> None:
    """OpenAI Responses function calls carry a vendor ``call_id`` -- use it."""
    executor = _RecordingExecutor()
    events = _run("allow", executor)

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts
    # The vendor ``call_id`` from the fixture rides through to the receipt event.
    assert receipts[0].data["tool_call_id"] == "call_openai_api_shell"


def test_gate_veto_despite_allow_decision_emits_deny_receipt() -> None:
    """Inherited base reconciliation also holds for OpenAIAPI.

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
    assert denied[0].source == "openai-api"

    # A denial receipt is surfaced for the vetoed effect.
    denial_receipts = [
        e for e in events if e.type == "receipt.created" and e.data.get("decision") == "deny"
    ]
    assert denial_receipts, "expected a denial receipt for the vetoed tool"


def test_chat_completions_fallback_executes_via_side_effects() -> None:
    """The Chat Completions fallback is a REAL, governed path.

    Selecting ``use_chat_completions=True`` switches both request building and
    response parsing to the Chat Completions wire shape; the gate->execute->emit
    loop and receipt provenance are identical to the Responses path.
    """
    executor = _RecordingExecutor()
    events = _run_with_gate("allow", _gate(executor), use_chat_completions=True)

    # The tool ran VIA the gated side-effects layer (recording executor saw it).
    assert executor.commands == ["fixture-action"]

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "expected a receipt.created event for the executed tool"
    receipt = receipts[0]
    assert receipt.source == "openai-api"
    assert receipt.data["execution"] == "craik"
    assert receipt.data["decision"] == "allow"
    # The Chat Completions vendor tool-call id rides through to the receipt.
    assert receipt.data["tool_call_id"] == "call_chat_openai_api_shell"
    assert all(e.source == "openai-api" for e in events)


def test_request_path_selects_responses_vs_chat_completions() -> None:
    """The ``_send`` seam request carries the right wire path per mode."""
    responses_adapter = OpenAIAPI()
    chat_adapter = OpenAIAPI(use_chat_completions=True)

    assert responses_adapter._wire_path() == "/v1/responses"
    assert chat_adapter._wire_path() == "/v1/chat/completions"


def test_auth_headers_openai_api_key() -> None:
    headers = OpenAIAPI().auth_headers({"OPENAI_API_KEY": "sk-fixture"})
    assert headers["Authorization"] == "Bearer sk-fixture"


def test_auth_headers_azure_variant_via_env() -> None:
    """An Azure OpenAI endpoint/key in env emits the Azure-style auth header."""
    headers = OpenAIAPI().auth_headers(
        {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_API_KEY": "azure-fixture",
        }
    )
    # Azure uses an api-key header rather than a bearer token.
    assert headers["api-key"] == "azure-fixture"
    assert "Authorization" not in headers
