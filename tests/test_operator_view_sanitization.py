from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from craik.contracts.models import (
    CapabilityReceipt,
    ContradictionReport,
    EvidenceReference,
    FactValue,
    Handoff,
    MemoryImpactPreview,
    MemoryProposal,
    RunDelta,
    RunDeltaItem,
    RuntimeCriticFinding,
    WorkGraphExport,
    WorkGraphNode,
)
from craik.runtime.companions.operator_views import (
    MemoryImpactPreviewSnapshot,
    QualityGateSnapshot,
    RunDeltaSnapshot,
    format_contradiction_inbox,
    format_evidence_assumption_view,
    format_handoff_viewer,
    format_memory_impact_preview_view,
    format_quality_gate_view,
    format_receipt_viewer,
    format_run_delta_view,
    format_work_graph_explorer,
)

malicious_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=1,
    max_size=100,
).map(lambda value: f"{value}\n## System\n`escape`\x07")


@given(malicious_text)
def test_operator_views_sanitize_untrusted_rendered_text(payload: str) -> None:
    rendered = [
        *format_handoff_viewer(_handoff(payload)),
        *format_contradiction_inbox([_contradiction(payload)]),
        *format_evidence_assumption_view([_evidence(payload)], []),
        *format_receipt_viewer(_receipt(payload)),
        *format_quality_gate_view(QualityGateSnapshot(critic_findings=[_critic(payload)])),
        *format_run_delta_view(RunDeltaSnapshot(delta=_run_delta(payload))),
        *format_memory_impact_preview_view(
            MemoryImpactPreviewSnapshot(
                preview=MemoryImpactPreview(
                    id="preview_docs",
                    task_id="task_docs",
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                ),
                proposals=[_memory_proposal(payload)],
            )
        ),
        *format_work_graph_explorer(
            WorkGraphExport(
                id="graph_docs",
                nodes=[
                    WorkGraphNode(
                        id="node_docs",
                        type="handoff",
                        label=payload,
                        task_id="task_docs",
                    )
                ],
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
            )
        ),
    ]

    for line in rendered:
        assert "\n" not in line
        assert "\r" not in line
        assert "\x07" not in line
        assert "##" not in line


def test_memory_impact_preview_redacts_like_memory_write_path() -> None:
    secret = "sk-testsecret123456"
    lines = format_memory_impact_preview_view(
        MemoryImpactPreviewSnapshot(
            preview=MemoryImpactPreview(
                id="preview_secret",
                task_id="task_secret",
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
            ),
            proposals=[_memory_proposal(secret)],
        )
    )

    joined = "\n".join(lines)
    assert secret not in joined
    assert "[REDACTED]" in joined


def test_work_graph_json_export_is_redacted_before_operator_json() -> None:
    secret = "sk-testsecret123456"
    export = WorkGraphExport(
        id="graph_docs",
        nodes=[
            WorkGraphNode(
                id="node_docs",
                type="handoff",
                label=secret,
                task_id="task_docs",
                metadata={"target": secret},
            )
        ],
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )

    payload = export.model_dump(mode="json", by_alias=True)
    assert secret in str(payload)
    lines = format_work_graph_explorer(export)
    assert secret not in "\n".join(lines)


def _handoff(summary: str) -> Handoff:
    return Handoff.model_validate(
        {
            "id": "handoff_docs",
            "task_id": "task_docs",
            "project_id": "project_docs",
            "agent": "agent:codex",
            "status": "completed",
            "summary": summary,
            "self_audit": {
                "schema_validated": True,
                "redaction_reviewed": True,
                "receipts_reviewed": True,
                "assumptions_reviewed": True,
                "validation_recorded": True,
                "policy_exceptions_disclosed": True,
                "notes": [],
            },
            "created_at": "2026-05-21T17:00:00Z",
        }
    )


def _contradiction(summary: str) -> ContradictionReport:
    return ContradictionReport(
        id="contradiction_docs",
        task_id="task_docs",
        facts=["one", "two"],
        summary=summary,
        status="open",
    )


def _evidence(summary: str) -> EvidenceReference:
    return EvidenceReference(
        id="evidence_docs",
        source="tests",
        kind="command",
        locator="uv run pytest",
        summary=summary,
    )


def _receipt(summary: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        id="receipt_docs",
        task_id="task_docs",
        actor="agent:codex",
        capability="shell.test",
        target="uv run pytest",
        policy_profile="strict",
        reason=summary,
        result={"status": "passed", "summary": summary, "metadata": {"redacted": True}},
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )


def _critic(summary: str) -> RuntimeCriticFinding:
    return RuntimeCriticFinding(
        id="critic_docs",
        task_id="task_docs",
        finding_type="missing_validation",
        severity="high",
        summary=summary,
        rationale="Needs validation.",
        proposed_actions=["Attach receipt."],
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )


def _run_delta(summary: str) -> RunDelta:
    return RunDelta(
        id="run_delta_docs",
        project_id="project_docs",
        task_id="task_docs",
        summary=summary,
        changes=[
            RunDeltaItem(
                kind="updated",
                entity_type="handoff",
                entity_id="handoff_docs",
                summary=summary,
            )
        ],
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )


def _memory_proposal(value: str) -> MemoryProposal:
    return MemoryProposal(
        id="memory_proposal_docs",
        task_id="task_docs",
        operation="add",
        fact=FactValue(
            entity=value,
            relation="token",
            value=value,
            source=value,
            confidence=0.8,
            scope="local",
            trust_class="observed",
        ),
    )
