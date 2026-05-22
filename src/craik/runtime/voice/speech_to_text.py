"""Speech-to-text adapter contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.policy.redaction import REDACTION, redact

SpeechToTextStatus = Literal["completed", "partial", "failed"]

_PRIVATE_STT_KEYS = {
    "audio",
    "audio_payload",
    "audio_bytes",
    "payload",
    "private_transcript_metadata",
    "raw_audio",
    "raw_payload",
    "waveform",
}


class SpeechToTextInputMetadata(CraikModel):
    """Reference metadata for audio sent to a speech-to-text adapter."""

    media_artifact_id: str
    media_mime_type: str
    duration_ms: int | None = Field(default=None, ge=0)
    language_hint: str | None = None
    channel_count: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechToTextTranscriptSegment(CraikModel):
    """One transcript segment with optional timing and confidence."""

    text: str
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_segment_timing(self) -> SpeechToTextTranscriptSegment:
        """Keep segment timing ordered when both endpoints are present."""
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("segment end_ms must be greater than or equal to start_ms")
        return self


class SpeechToTextTranscript(CraikModel):
    """Redacted transcript returned by a speech-to-text adapter."""

    text: str
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    segments: list[SpeechToTextTranscriptSegment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = True


class SpeechToTextResult(CraikModel):
    """Policy-, evidence-, and receipt-linked speech-to-text result."""

    id: str
    task_id: str
    adapter_id: str
    status: SpeechToTextStatus
    input: SpeechToTextInputMetadata
    transcript: SpeechToTextTranscript | None = None
    errors: list[str] = Field(default_factory=list)
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    redacted_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_speech_to_text_result(self) -> SpeechToTextResult:
        """Keep STT results policy-bound and internally consistent."""
        if not self.policy_envelope_id:
            raise ValueError("speech-to-text results require policy_envelope_id")
        if self.status in {"completed", "partial"} and self.transcript is None:
            raise ValueError("completed or partial speech-to-text results require transcript")
        if self.status == "failed" and not self.errors:
            raise ValueError("failed speech-to-text results require errors")
        return self


def speech_to_text_result(
    *,
    result_id: str,
    task_id: str,
    adapter_id: str,
    status: SpeechToTextStatus,
    input_metadata: SpeechToTextInputMetadata,
    policy_envelope_id: str,
    evidence_ids: list[str],
    receipt_ids: list[str],
    transcript: SpeechToTextTranscript | None = None,
    errors: list[str] | None = None,
    created_at: datetime | None = None,
) -> SpeechToTextResult:
    """Build a redacted speech-to-text result."""
    redacted_paths: list[str] = []
    safe_input = input_metadata.model_copy(
        update={"metadata": _safe_metadata(input_metadata.metadata, redacted_paths)}
    )
    safe_transcript = None
    if transcript is not None:
        safe_transcript = transcript.model_copy(
            update={
                "text": str(_safe_value(transcript.text, redacted_paths)),
                "segments": _safe_segments(transcript.segments, redacted_paths),
                "metadata": _safe_metadata(transcript.metadata, redacted_paths),
            }
        )
    safe_errors = [str(_safe_value(error, redacted_paths)) for error in errors or []]

    return SpeechToTextResult(
        id=result_id,
        task_id=task_id,
        adapter_id=adapter_id,
        status=status,
        input=safe_input,
        transcript=safe_transcript,
        errors=safe_errors,
        policy_envelope_id=policy_envelope_id,
        evidence_ids=evidence_ids,
        receipt_ids=receipt_ids,
        redacted_paths=sorted(set(redacted_paths)),
        created_at=created_at or datetime.now(UTC),
    )


def _safe_metadata(metadata: dict[str, Any], redacted_paths: list[str]) -> dict[str, Any]:
    safe = _safe_value(metadata, redacted_paths)
    if isinstance(safe, dict):
        return safe
    return {}


def _safe_segments(
    segments: list[SpeechToTextTranscriptSegment],
    redacted_paths: list[str],
) -> list[SpeechToTextTranscriptSegment]:
    return [
        segment.model_copy(update={"text": str(_safe_value(segment.text, redacted_paths))})
        for segment in segments
    ]


def _safe_value(value: Any, redacted_paths: list[str]) -> Any:
    redacted = redact(value)
    redacted_paths.extend(redacted.redacted_paths)
    return _drop_private_stt_payloads(redacted.value, "$", redacted_paths)


def _drop_private_stt_payloads(value: Any, path: str, redacted_paths: list[str]) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}"
            normalized = str(key).lower().replace("-", "_")
            if normalized in _PRIVATE_STT_KEYS:
                safe[key] = REDACTION
                redacted_paths.append(child_path)
            else:
                safe[key] = _drop_private_stt_payloads(item, child_path, redacted_paths)
        return safe
    if isinstance(value, list):
        return [
            _drop_private_stt_payloads(item, f"{path}[{index}]", redacted_paths)
            for index, item in enumerate(value)
        ]
    return value
