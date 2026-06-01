"""Task 5.7 parity item C: AnthropicCLI.run() persists gateway event history.

The legacy claude path persisted a redacted gateway-event-history ``RunOutput``
(``_persist_gateway_event_history``) like the provider path did; the 5.5a review
flagged that ``AnthropicCLI.run()`` omitted it. With execute_prompt now on
run(), the typed claude run() must persist that artifact too, for parity with the
provider / generic-CLI run() paths (both of which already do).
"""

from __future__ import annotations

from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.audited_core import ClaudeCoreResult
from craik.runtime.backend.adapters.base import RunContext


def test_anthropic_cli_run_persists_gateway_event_history(monkeypatch) -> None:
    payload = {
        "backend": "claude-code",
        "status": "completed",
        "run": {"id": "run_hist", "task_id": "task_hist"},
        "task": {"id": "task_hist"},
        "receipt_ids": ["receipt_hist"],
    }

    def _fake_core(*, prompt, env, require_operator_approval, stream):  # noqa: ANN001
        return ClaudeCoreResult(
            payload=payload,
            run_id="run_hist",
            task_id="task_hist",
            status="completed",
            receipt_ids=["receipt_hist"],
        )

    persisted: list[tuple[dict, int]] = []

    def _fake_persist(p, events, *, store=None, env=None):  # noqa: ANN001
        persisted.append((p, len(events)))

    monkeypatch.setattr(
        "craik.runtime.backend.adapters.audited_core.run_claude_code_core",
        _fake_core,
    )
    monkeypatch.setattr(
        "craik.runtime.backend.session._persist_gateway_event_history",
        _fake_persist,
    )

    adapter = AnthropicCLI(original_env={})
    ctx = RunContext(
        prompt="hello",
        env={},
        emit=lambda _e: None,
        decide=lambda _r: "allow",
        require_operator_approval=False,
    )
    events = list(adapter.run(ctx))

    assert persisted, "AnthropicCLI.run() must persist gateway event history"
    persisted_payload, event_count = persisted[0]
    assert persisted_payload is payload
    # The persisted event count matches the events the run yielded.
    assert event_count == len(events)
