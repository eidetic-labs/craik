"""Task 5.7 parity item C: CLI receipts only attribute ``operator`` when gated.

Pre-cutover the CLI receipt mappers hardcoded ``decided_by="operator"`` with a
TODO. Now that gating is live, an ``operator``-attributed receipt must persist
ONLY when an operator actually decided (a gated run). An ungated / auto run
(``require_operator_approval=False``) reflects the TRUE posture: ``decided_by=
"bypass"`` (the ungoverned/observe flag) -- never a falsely-attributed operator
decision.
"""

from __future__ import annotations

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.events import BackendEvent


def _ctx(*, require_operator_approval: bool) -> RunContext:
    return RunContext(
        prompt="hello",
        env={},
        emit=lambda _event: None,
        decide=lambda _request: "allow",
        require_operator_approval=require_operator_approval,
    )


def _run_events(adapter, ctx: RunContext) -> list[BackendEvent]:
    return list(adapter.run(ctx))


def test_anthropic_cli_ungated_run_does_not_attribute_operator(monkeypatch) -> None:
    """An ungated AnthropicCLI run reflects ``bypass``, not ``operator``."""
    from craik.runtime.backend.adapters import anthropic_cli
    from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI

    captured: list[BackendEvent] = []

    def _fake_core(*, prompt, env, require_operator_approval, stream):  # noqa: ANN001
        # No native stream lines; just a structured result for framing.
        from craik.runtime.backend.adapters.audited_core import ClaudeCoreResult

        return ClaudeCoreResult(
            payload={"backend": "claude-code", "status": "completed"},
            run_id="run_x",
            task_id="task_x",
            status="completed",
            receipt_ids=["receipt_run_x"],
        )

    monkeypatch.setattr(anthropic_cli, "run_claude_code_core", _fake_core, raising=False)
    # Patch the import target used inside run().
    monkeypatch.setattr(
        "craik.runtime.backend.adapters.audited_core.run_claude_code_core",
        _fake_core,
    )

    adapter = AnthropicCLI(original_env={})
    captured = _run_events(adapter, _ctx(require_operator_approval=False))

    receipts = [event for event in captured if event.type == "receipt.created"]
    assert receipts, "framing emits at least one receipt"
    assert all(receipt.data["decided_by"] == "bypass" for receipt in receipts)
    assert all(receipt.data["execution"] == "delegated-observed" for receipt in receipts)


def test_anthropic_cli_gated_run_attributes_operator(monkeypatch) -> None:
    """A gated AnthropicCLI run (operator decided) attributes ``operator``."""
    from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
    from craik.runtime.backend.adapters.audited_core import ClaudeCoreResult

    def _fake_core(*, prompt, env, require_operator_approval, stream):  # noqa: ANN001
        return ClaudeCoreResult(
            payload={"backend": "claude-code", "status": "completed"},
            run_id="run_x",
            task_id="task_x",
            status="completed",
            receipt_ids=["receipt_run_x"],
        )

    monkeypatch.setattr(
        "craik.runtime.backend.adapters.audited_core.run_claude_code_core",
        _fake_core,
    )

    adapter = AnthropicCLI(original_env={})
    captured = _run_events(adapter, _ctx(require_operator_approval=True))

    receipts = [event for event in captured if event.type == "receipt.created"]
    assert receipts
    assert all(receipt.data["decided_by"] == "operator" for receipt in receipts)
