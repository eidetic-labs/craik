from __future__ import annotations

from pathlib import Path

from craik.runtime.backend.replay import load_gateway_replay, summarize_gateway_replay


def test_gateway_replay_fixture_has_client_evaluation_contract() -> None:
    events = load_gateway_replay(Path("tests/fixtures/gateway/prompt_run.jsonl"))

    summary = summarize_gateway_replay(events)

    assert summary.has_lifecycle
    assert summary.has_working_state
    assert "run.working" in summary.event_types
    assert summary.run_ids == ["run_review_the_plan"]
    assert summary.task_ids == ["task_review_the_plan"]
    assert summary.receipt_ids == ["receipt_run_review_the_plan_claude_code"]
    assert summary.progress_messages == ["Preparing audited Claude Code run."]


def test_claude_code_replay_fixture_has_structured_activity_contract() -> None:
    events = load_gateway_replay(Path("tests/fixtures/gateway/claude_code_stream.jsonl"))

    summary = summarize_gateway_replay(events)

    assert summary.has_lifecycle
    assert summary.has_working_state
    assert summary.has_claude_activity
    assert "tool.used" in summary.event_types
    assert "file.changed" in summary.event_types
    assert "approval.requested" in summary.event_types
    assert "run.output" in summary.event_types
    assert summary.tool_names == ["Read", "Grep", "Bash"]
    assert summary.file_paths == [
        "/Users/bjones/Desktop/Craik_Backend_Plan.md",
        "src/craik/runtime/backend",
        "src/craik/runtime/backend/session.py",
    ]
    assert summary.commands == ["uv run pytest tests/test_backend_gateway_session.py"]
    assert summary.approval_requests == [
        (
            "Claude Code requests approval for `Edit` on "
            "`src/craik/runtime/backend/session.py`: normalize stream event mapping"
        )
    ]
    assert summary.run_ids == ["run_review_desktop_plan"]
    assert summary.task_ids == ["task_review_desktop_plan"]
    assert summary.receipt_ids == [
        "receipt_review_desktop_plan_claude_code_approval",
        "receipt_run_review_desktop_plan_claude_code",
    ]
