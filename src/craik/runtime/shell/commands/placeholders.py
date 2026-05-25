"""CommandResult helpers for v0.12.8 slash command placeholders."""

from __future__ import annotations

from craik.runtime.contract import CommandResult, NextAction


def compact_stub_result() -> CommandResult:
    """Return the registered placeholder for future context compression."""
    payload = {
        "status": "Coming in v0.14.0",
        "description": (
            "Conversation compression will let you manually compress the conversation "
            "when context tightens. Craik will summarize prior turns into a structured "
            "digest while preserving enough state to answer follow-up questions about "
            "earlier conversation turns."
        ),
        "implementation_target": "v0.14.0 G1",
        "workaround": (
            "Start a new session with /clear, or use session export to checkpoint "
            "manually."
        ),
    }
    return CommandResult(
        payload=payload,
        shape="kv",
        text=(
            "Coming in v0.14.0\n\n"
            "Conversation compression will let you manually compress the conversation "
            "when context tightens. Craik will summarize prior turns into a structured "
            "digest while preserving enough state to answer follow-up questions about "
            "earlier conversation turns.\n\n"
            "This slash command is registered as a placeholder so it appears in /help. "
            "The full implementation lands with v0.14.0 G1.\n\n"
            "Workaround until then: start a new session with /clear, or use session "
            "export to checkpoint manually."
        ),
        exit_code=2,
        next_actions=[
            NextAction(
                text="Open compression target scope",
                command="/help compact",
                field="implementation_target",
            )
        ],
    )


def share_stub_result() -> CommandResult:
    """Return the registered placeholder for future transcript sharing."""
    payload = {
        "status": "Coming in v0.13.0",
        "description": (
            "Transcript sharing will generate a shareable link to the current session, "
            "served from the public docs domain. Recipients will read the transcript "
            "without authenticating against the source operator's Craik instance."
        ),
        "implementation_target": "v0.13.0 G8",
        "workaround": (
            "Use craik session export-portable for a redacted shareable bundle until "
            "the public sharing flow lands."
        ),
    }
    return CommandResult(
        payload=payload,
        shape="kv",
        text=(
            "Coming in v0.13.0\n\n"
            "Transcript sharing will generate a shareable link to the current session, "
            "served from the public docs domain. Recipients will read the transcript "
            "without authenticating against the source operator's Craik instance.\n\n"
            "This slash command is registered as a placeholder. The full implementation "
            "lands when v0.13.0 G8 brings the public docs site live.\n\n"
            "Workaround until then: use craik session export-portable for a redacted "
            "shareable bundle."
        ),
        exit_code=2,
        next_actions=[
            NextAction(
                text="Open sharing target scope",
                command="/help share",
                field="implementation_target",
            )
        ],
    )
