from __future__ import annotations

from pathlib import Path

from craik.runtime.backend.replay import load_gateway_replay, summarize_gateway_replay


def test_gateway_replay_fixture_has_client_evaluation_contract() -> None:
    events = load_gateway_replay(Path("tests/fixtures/gateway/prompt_run.jsonl"))

    summary = summarize_gateway_replay(events)

    assert summary.has_lifecycle
    assert summary.has_working_state
    assert summary.run_ids == ["run_review_the_plan"]
    assert summary.task_ids == ["task_review_the_plan"]
    assert summary.receipt_ids == ["receipt_run_review_the_plan_claude_code"]
    assert summary.progress_messages == ["Preparing audited Claude Code run."]
