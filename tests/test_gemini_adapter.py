from datetime import UTC, datetime

import pytest

from craik.contracts.models import CompiledPrompt, PromptSection, RunnerAdapterRequest
from craik.runtime.runners.google_adapter import (
    GeminiRunnerAdapter,
    GeminiRunnerRequestError,
    request_from_compiled_prompt,
)
from craik.runtime.runners.runners import RunnerAdapter, get_runner_capability_matrix


def test_gemini_adapter_fixture_success_returns_normalized_outputs() -> None:
    compiled = _compiled_prompt()
    request = request_from_compiled_prompt(
        compiled,
        created_at=datetime(2026, 5, 16, 6, 0, tzinfo=UTC),
        context={"tests_run": ["uv run pytest"], "next_steps": ["Record findings."]},
    )
    adapter = GeminiRunnerAdapter()

    result = adapter.run(request)

    assert isinstance(adapter, RunnerAdapter)
    assert result.status == "completed"
    assert result.runner.id == "google"
    assert result.runner.adapter_version == "0.2.0-preview"
    assert result.runner.metadata["adapter_mode"] == "fixture"
    assert result.outputs["prompt_handoff"]["prompt"] == compiled.prompt
    assert result.outputs["handoff_input"]["agent"] == "runner:google"
    assert result.outputs["handoff_input"]["status"] == "completed"
    assert result.outputs["receipt_inputs"][0]["capability_grant_id"] == "grant_review_comment"
    assert result.outputs["receipt_inputs"][0]["result"]["status"] == "passed"
    assert result.artifacts == [compiled.case_file_id, compiled.policy_envelope_id]
    assert "fixture/prompt-handoff mode used" in result.diagnostics[0]


def test_gemini_adapter_fixture_blocked_output() -> None:
    request = request_from_compiled_prompt(
        _compiled_prompt(),
        created_at=datetime(2026, 5, 16, 6, 1, tzinfo=UTC),
        context={
            "fixture_status": "blocked",
            "blocked_reason": "memory.write is unsupported",
            "risks": ["Gemini profile is read/review-oriented."],
        },
    )

    result = GeminiRunnerAdapter().run(request)

    assert result.status == "blocked"
    assert "memory.write is unsupported" in result.summary
    assert result.outputs["handoff_input"]["status"] == "blocked"
    assert result.outputs["handoff_input"]["risks"] == ["Gemini profile is read/review-oriented."]
    assert result.outputs["receipt_inputs"][0]["result"]["status"] == "blocked"


def test_gemini_adapter_fixture_failure_output() -> None:
    request = request_from_compiled_prompt(
        _compiled_prompt(),
        created_at=datetime(2026, 5, 16, 6, 2, tzinfo=UTC),
        context={
            "fixture_status": "failed",
            "failure_reason": "prompt handoff response missing",
            "diagnostics": ["missing response"],
        },
    )

    result = GeminiRunnerAdapter().run(request)

    assert result.status == "failed"
    assert "prompt handoff response missing" in result.summary
    assert result.outputs["handoff_input"]["status"] == "failed"
    assert result.outputs["receipt_inputs"][0]["result"]["status"] == "failed"
    assert "missing response" in result.diagnostics


def test_gemini_adapter_rejects_wrong_runner_request() -> None:
    request = request_from_compiled_prompt(_compiled_prompt())
    codex = get_runner_capability_matrix("codex").runner
    wrong_runner = RunnerAdapterRequest.model_validate(
        {**request.model_dump(mode="json", by_alias=True), "runner": codex}
    )

    with pytest.raises(GeminiRunnerRequestError, match="cannot run"):
        GeminiRunnerAdapter().run(wrong_runner)


def test_gemini_request_builder_rejects_non_gemini_prompt() -> None:
    prompt = _compiled_prompt().model_copy(update={"runner_id": "claude"})

    with pytest.raises(GeminiRunnerRequestError, match="compiled prompt runner"):
        request_from_compiled_prompt(prompt)


def _compiled_prompt() -> CompiledPrompt:
    return CompiledPrompt(
        id="prompt_review_docs_gemini",
        task_id="task_review_docs",
        case_file_id="case_review_docs",
        policy_envelope_id="policy_task_review_docs",
        runner_id="google",
        runner_mode="prompt-handoff",
        capability_grant_ids=["grant_review_comment"],
        expected_output_schemas=["craik.runner_adapter_result", "craik.handoff"],
        context_omissions=["Memory facts were not loaded into the case file."],
        stop_conditions=["Stop before using denied capabilities."],
        sections=[PromptSection(title="Task", body="Review docs.")],
        prompt="## Task\nReview docs.",
    )
