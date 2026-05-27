"""Runner adapter protocol and fixture implementation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from craik.contracts.models import (
    RunnerAdapterRequest,
    RunnerAdapterResult,
    RunnerCapability,
    RunnerCapabilityMatrix,
    RunnerCapabilitySupport,
    RunnerMetadata,
    RunnerTrustProfile,
)

RUNNER_CAPABILITY_NAMES = (
    "file.read",
    "file.write",
    "shell.execute",
    "network.access",
    "memory.read",
    "memory.write",
    "review.comment",
    "result.structured",
)


@runtime_checkable
class RunnerAdapter(Protocol):
    """Interface future runner adapters must implement."""

    @property
    def metadata(self) -> RunnerMetadata:
        """Return stable runner identity and capability metadata."""

    def run(self, request: RunnerAdapterRequest) -> RunnerAdapterResult:
        """Run or guide one task request and return normalized output."""


@dataclass(frozen=True)
class FixtureRunnerAdapter:
    """Deterministic adapter for contract tests and adapter scaffolding."""

    metadata: RunnerMetadata
    result: RunnerAdapterResult

    def run(self, request: RunnerAdapterRequest) -> RunnerAdapterResult:
        """Return the configured fixture result after validating request linkage."""
        if request.runner.id != self.metadata.id:
            raise ValueError("runner request metadata does not match adapter metadata")
        if self.result.request_id != request.id:
            raise ValueError("runner fixture result does not match request id")
        return self.result


def default_runner_capability_matrices() -> dict[str, RunnerCapabilityMatrix]:
    """Return the built-in conservative runner matrix by runner id."""
    matrices = [
        _codex_matrix(),
        _claude_matrix(),
        _claude_code_matrix(),
        _gemini_matrix(),
        _fixture_matrix(),
        _provider_matrix(
            runner_id="provider_openai",
            name="OpenAI Provider Runner",
            provider_family="openai",
        ),
        _provider_matrix(
            runner_id="provider_openai_responses",
            name="OpenAI Responses Provider Runner",
            provider_family="openai",
        ),
        _provider_matrix(
            runner_id="provider_openai_chat",
            name="OpenAI Chat Completions Provider Runner",
            provider_family="chat_completions",
        ),
        _provider_matrix(
            runner_id="provider_local_openai_compatible",
            name="Local OpenAI-Compatible Provider Runner",
            provider_family="chat_completions",
        ),
        _provider_matrix(
            runner_id="provider_local_ollama",
            name="Ollama Local Provider Runner",
            provider_family="chat_completions",
        ),
        _provider_matrix(
            runner_id="provider_local_lm_studio",
            name="LM Studio Local Provider Runner",
            provider_family="chat_completions",
        ),
        _provider_matrix(
            runner_id="provider_local_vllm",
            name="vLLM Local Provider Runner",
            provider_family="chat_completions",
        ),
        _provider_matrix(
            runner_id="provider_anthropic",
            name="Anthropic Provider Runner",
            provider_family="anthropic",
        ),
        _provider_matrix(
            runner_id="provider_gemini",
            name="Gemini Provider Runner",
            provider_family="gemini",
        ),
        _provider_matrix(
            runner_id="provider_anthropic_messages",
            name="Anthropic Messages Provider Runner",
            provider_family="anthropic",
        ),
    ]
    return {matrix.runner.id: matrix for matrix in matrices}


def get_runner_capability_matrix(runner_id: str) -> RunnerCapabilityMatrix:
    """Return a built-in runner capability matrix by runner id."""
    try:
        return default_runner_capability_matrices()[runner_id]
    except KeyError:
        known = ", ".join(sorted(default_runner_capability_matrices()))
        raise KeyError(f"unknown runner {runner_id!r}; known runners: {known}") from None


def capability_supported(matrix: RunnerCapabilityMatrix, capability: str) -> bool:
    """Return whether a runner has direct support for a named capability."""
    return any(
        entry.name == capability and entry.support == "supported" for entry in matrix.capabilities
    )


def capability_requires_grant(matrix: RunnerCapabilityMatrix, capability: str) -> bool:
    """Return whether a supported or handoff capability requires an explicit grant."""
    for entry in matrix.capabilities:
        if entry.name == capability:
            return entry.grant_required
    return True


def _codex_matrix() -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id="codex",
            name="Codex",
            adapter="codex",
            adapter_version="preview",
            mode="live",
            capabilities=list(RUNNER_CAPABILITY_NAMES),
        ),
        trust=RunnerTrustProfile(
            level="medium",
            boundary="Local workspace runner with shell/tool access mediated by Craik policy.",
            default_grant_posture="prompt-for-approval",
            notes=[
                "Treat filesystem writes, shell execution, network, and memory writes as grants."
            ],
        ),
        capabilities=[
            _capability("file.read", "supported", grant_required=False),
            _capability("file.write", "supported"),
            _capability("shell.execute", "supported"),
            _capability("network.access", "supported"),
            _capability("memory.read", "supported", grant_required=False),
            _capability("memory.write", "supported"),
            _capability("review.comment", "supported"),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=[
            "Default to explicit grants for side effects.",
            (
                "Require receipts for writes, shell execution, network use, review comments, "
                "and memory writes."
            ),
        ],
    )


def _claude_matrix() -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id="claude",
            name="Claude",
            adapter="claude",
            adapter_version="preview",
            mode="prompt-handoff",
            capabilities=[
                "file.read",
                "file.write",
                "memory.read",
                "memory.write",
                "review.comment",
                "result.structured",
            ],
        ),
        trust=RunnerTrustProfile(
            level="medium",
            boundary=(
                "Prompt-handoff runner; Craik should treat side effects as proposed work "
                "until verified."
            ),
            default_grant_posture="deny-by-default",
            notes=[
                "Live tool authority depends on the external Claude environment, not Craik core."
            ],
        ),
        capabilities=[
            _capability("file.read", "prompt-handoff", grant_required=False),
            _capability("file.write", "prompt-handoff"),
            _capability("shell.execute", "unsupported"),
            _capability("network.access", "unsupported"),
            _capability("memory.read", "prompt-handoff", grant_required=False),
            _capability("memory.write", "prompt-handoff"),
            _capability("review.comment", "prompt-handoff"),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=[
            "Prompt-handoff side effects must return through Craik review and receipt workflows.",
        ],
    )


def _claude_code_matrix() -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id="claude-code",
            name="Claude Code",
            adapter="claude-code",
            adapter_version="preview",
            mode="live",
            capabilities=list(RUNNER_CAPABILITY_NAMES),
        ),
        trust=RunnerTrustProfile(
            level="medium",
            boundary=(
                "Local Claude Code CLI runner with workspace tool access controlled by Claude "
                "Code permission mode and Craik receipts."
            ),
            default_grant_posture="prompt-for-approval",
            notes=[
                "Treat file writes, shell execution, network access, review comments, and "
                "memory writes as auditable side effects."
            ],
        ),
        capabilities=[
            _capability("file.read", "supported", grant_required=False),
            _capability("file.write", "supported"),
            _capability("shell.execute", "supported"),
            _capability("network.access", "supported"),
            _capability("memory.read", "supported", grant_required=False),
            _capability("memory.write", "supported"),
            _capability("review.comment", "supported"),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=[
            (
                "Execute through the local Claude Code CLI when the operator selects the "
                + "claude-code backend."
            ),
            "Use Claude Code permission modes for edit and tool approval behavior.",
            "Record Craik receipts and handoffs for the delegated execution.",
        ],
    )


def _gemini_matrix() -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id="gemini",
            name="Gemini",
            adapter="gemini",
            adapter_version="preview",
            mode="prompt-handoff",
            capabilities=["file.read", "memory.read", "review.comment", "result.structured"],
        ),
        trust=RunnerTrustProfile(
            level="low",
            boundary=(
                "Prompt-handoff runner with conservative defaults until live adapter behavior "
                "is proven."
            ),
            default_grant_posture="deny-by-default",
            notes=["Use for review or synthesis by default; avoid direct side effects in v0.1.0."],
        ),
        capabilities=[
            _capability("file.read", "prompt-handoff", grant_required=False),
            _capability("file.write", "unsupported"),
            _capability("shell.execute", "unsupported"),
            _capability("network.access", "unsupported"),
            _capability("memory.read", "prompt-handoff", grant_required=False),
            _capability("memory.write", "unsupported"),
            _capability("review.comment", "prompt-handoff"),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=[
            "Keep default Gemini use read/review-oriented until adapter tests justify more."
        ],
    )


def _fixture_matrix() -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id="fixture",
            name="Fixture Runner",
            adapter="fixture",
            adapter_version="0.1.0",
            mode="fixture",
            capabilities=["result.structured"],
        ),
        trust=RunnerTrustProfile(
            level="high",
            boundary="Deterministic in-process fixture for tests; no external side effects.",
            default_grant_posture="allow-with-receipt",
            requires_receipts=False,
            notes=["Only use for fixtures and contract tests."],
        ),
        capabilities=[
            _capability("file.read", "unsupported"),
            _capability("file.write", "unsupported"),
            _capability("shell.execute", "unsupported"),
            _capability("network.access", "unsupported"),
            _capability("memory.read", "unsupported"),
            _capability("memory.write", "unsupported"),
            _capability("review.comment", "unsupported"),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=["Fixture runs should not widen runtime authority."],
    )


def _provider_matrix(
    *,
    runner_id: str,
    name: str,
    provider_family: str,
) -> RunnerCapabilityMatrix:
    return RunnerCapabilityMatrix(
        runner=RunnerMetadata(
            id=runner_id,
            name=name,
            adapter="provider-runtime",
            adapter_version="0.1.0",
            mode="live",
            capabilities=[
                "model.chat",
                "model.streaming",
                "model.tool_calls",
                "model.structured_output",
                "model.usage_metadata",
                "result.structured",
            ],
            metadata={"provider_family": provider_family},
        ),
        trust=RunnerTrustProfile(
            level="medium",
            boundary=(
                "Third-party model provider mediated by Craik provider runtime, "
                "secret references, receipts, and redaction."
            ),
            default_grant_posture="prompt-for-approval",
            notes=["Live calls require explicit provider runtime configuration."],
        ),
        capabilities=[
            _capability("file.read", "unsupported"),
            _capability("file.write", "unsupported"),
            _capability("shell.execute", "unsupported"),
            _capability("network.access", "supported"),
            _capability("memory.read", "unsupported"),
            _capability("memory.write", "unsupported"),
            _capability("review.comment", "unsupported"),
            _capability("model.chat", "supported"),
            _capability("model.streaming", "supported"),
            _capability("model.tool_calls", "supported"),
            _capability("model.structured_output", "supported"),
            _capability("model.usage_metadata", "supported", grant_required=False),
            _capability("result.structured", "supported", grant_required=False),
        ],
        policy_notes=[
            "Provider runs must use secret references, not raw credentials.",
            "Provider request and response metadata must be covered by receipts.",
        ],
    )


def _capability(
    name: str,
    support: RunnerCapabilitySupport,
    *,
    grant_required: bool = True,
    notes: str | None = None,
) -> RunnerCapability:
    return RunnerCapability(
        name=name,
        support=support,
        grant_required=grant_required,
        notes=notes,
    )


if not TYPE_CHECKING:
    __all__ = [name for name in globals() if not name.startswith("_")]
