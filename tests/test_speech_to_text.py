from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.runtime.voice.speech_to_text import (
    SpeechToTextInputMetadata,
    SpeechToTextResult,
    SpeechToTextTranscript,
    SpeechToTextTranscriptSegment,
    speech_to_text_result,
)

NOW = datetime(2026, 5, 16, 18, 5, tzinfo=UTC)


def test_speech_to_text_result_records_transcript_context() -> None:
    result = speech_to_text_result(
        result_id="stt_result_operator_note",
        task_id="task_operator_note",
        adapter_id="stt_adapter_fixture",
        status="completed",
        input_metadata=_input_metadata(),
        transcript=_transcript(),
        policy_envelope_id="policy_voice",
        evidence_ids=["evidence_audio_reference"],
        receipt_ids=["receipt_stt"],
        created_at=NOW,
    )

    assert result.status == "completed"
    assert result.input.media_artifact_id == "media_operator_note"
    assert result.transcript is not None
    assert result.transcript.text == "Create a follow-up task."
    assert result.transcript.confidence == 0.94
    assert result.policy_envelope_id == "policy_voice"
    assert result.evidence_ids == ["evidence_audio_reference"]
    assert result.receipt_ids == ["receipt_stt"]
    assert result.created_at == NOW


def test_speech_to_text_result_redacts_audio_payloads_and_private_metadata() -> None:
    result = speech_to_text_result(
        result_id="stt_result_operator_note",
        task_id="task_operator_note",
        adapter_id="stt_adapter_fixture",
        status="completed",
        input_metadata=_input_metadata(
            metadata={
                "audio_payload": "raw bytes",
                "api_token": "redaction-fixture-value",
                "source": "operator upload",
            }
        ),
        transcript=_transcript(
            text="operator said token=redactionfixture123",
            metadata={
                "private_transcript_metadata": {"speaker": "private"},
                "confidence_model": "fixture",
            },
            segments=[
                SpeechToTextTranscriptSegment(
                    text="segment token=redactionfixture123",
                    start_ms=0,
                    end_ms=1200,
                )
            ],
        ),
        policy_envelope_id="policy_voice",
        evidence_ids=["evidence_audio_reference"],
        receipt_ids=["receipt_stt"],
        created_at=NOW,
    )

    assert result.input.metadata["audio_payload"] == "[REDACTED]"
    assert result.input.metadata["api_token"] == "[REDACTED]"
    assert result.input.metadata["source"] == "operator upload"
    assert result.transcript is not None
    assert result.transcript.text == "operator said token=[REDACTED]"
    assert result.transcript.segments[0].text == "segment token=[REDACTED]"
    assert result.transcript.metadata["private_transcript_metadata"] == "[REDACTED]"
    assert result.transcript.metadata["confidence_model"] == "fixture"
    assert result.redacted_paths


def test_failed_speech_to_text_result_requires_errors() -> None:
    with pytest.raises(ValidationError, match="errors"):
        SpeechToTextResult(
            id="stt_result_failed",
            task_id="task_operator_note",
            adapter_id="stt_adapter_fixture",
            status="failed",
            input=_input_metadata(),
            policy_envelope_id="policy_voice",
            evidence_ids=["evidence_audio_reference"],
            receipt_ids=["receipt_stt"],
            created_at=NOW,
        )


def test_completed_speech_to_text_result_requires_transcript() -> None:
    with pytest.raises(ValidationError, match="transcript"):
        SpeechToTextResult(
            id="stt_result_missing_transcript",
            task_id="task_operator_note",
            adapter_id="stt_adapter_fixture",
            status="completed",
            input=_input_metadata(),
            policy_envelope_id="policy_voice",
            evidence_ids=["evidence_audio_reference"],
            receipt_ids=["receipt_stt"],
            created_at=NOW,
        )


def test_speech_to_text_result_requires_policy_evidence_and_receipts() -> None:
    with pytest.raises(ValidationError, match="policy_envelope_id"):
        speech_to_text_result(
            result_id="stt_result_operator_note",
            task_id="task_operator_note",
            adapter_id="stt_adapter_fixture",
            status="completed",
            input_metadata=_input_metadata(),
            transcript=_transcript(),
            policy_envelope_id="",
            evidence_ids=["evidence_audio_reference"],
            receipt_ids=["receipt_stt"],
        )

    with pytest.raises(ValidationError):
        speech_to_text_result(
            result_id="stt_result_operator_note",
            task_id="task_operator_note",
            adapter_id="stt_adapter_fixture",
            status="completed",
            input_metadata=_input_metadata(),
            transcript=_transcript(),
            policy_envelope_id="policy_voice",
            evidence_ids=[],
            receipt_ids=["receipt_stt"],
        )

    with pytest.raises(ValidationError):
        speech_to_text_result(
            result_id="stt_result_operator_note",
            task_id="task_operator_note",
            adapter_id="stt_adapter_fixture",
            status="completed",
            input_metadata=_input_metadata(),
            transcript=_transcript(),
            policy_envelope_id="policy_voice",
            evidence_ids=["evidence_audio_reference"],
            receipt_ids=[],
        )


def test_speech_to_text_segment_timing_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="end_ms"):
        SpeechToTextTranscriptSegment(text="bad timing", start_ms=200, end_ms=100)


def _input_metadata(**overrides: object) -> SpeechToTextInputMetadata:
    payload = {
        "media_artifact_id": "media_operator_note",
        "media_mime_type": "audio/wav",
        "duration_ms": 2400,
        "language_hint": "en-US",
        "channel_count": 1,
        "metadata": {"capture": "push_to_talk"},
    }
    payload.update(overrides)
    return SpeechToTextInputMetadata.model_validate(payload)


def _transcript(**overrides: object) -> SpeechToTextTranscript:
    payload = {
        "text": "Create a follow-up task.",
        "language": "en-US",
        "confidence": 0.94,
        "segments": [
            SpeechToTextTranscriptSegment(
                text="Create a follow-up task.",
                start_ms=0,
                end_ms=2100,
                confidence=0.94,
            )
        ],
        "metadata": {"redaction": "complete"},
    }
    payload.update(overrides)
    return SpeechToTextTranscript.model_validate(payload)
