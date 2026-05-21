from datetime import UTC, datetime, timedelta

from craik.contracts.models import (
    Assumption,
    CapabilityReceipt,
    ContextDebtRecord,
    ContextRequest,
    ContradictionReport,
    DistilledInstructionProposal,
    EvidenceCoverageScore,
    EvidenceReference,
    Handoff,
    HandoffQualityScore,
    HumanDelegationPoint,
    InstructionPromotionReview,
    InstructionProvenance,
    InstructionSource,
    InstructionSourceSnapshot,
    KnownTrap,
    MemoryImpactPreview,
    MemoryProposal,
    NegativeKnowledge,
    PluginReceipt,
    RecoverySession,
    RedTeamFinding,
    RunDelta,
    RuntimeCriticFinding,
    UnknownRecord,
    WorkGraphEdge,
    WorkGraphExport,
    WorkGraphNode,
)
from craik.runtime.companions.operator_views import (
    BudgetQuotaSnapshot,
    InstructionDistillationSnapshot,
    KnowledgeResolutionSnapshot,
    KnownTrapsSnapshot,
    MemoryImpactPreviewSnapshot,
    QualityGateSnapshot,
    RunDeltaSnapshot,
    format_budget_quota_view,
    format_contradiction_inbox,
    format_delegation_queue,
    format_evidence_assumption_view,
    format_handoff_viewer,
    format_instruction_distillation_view,
    format_knowledge_resolution_view,
    format_known_traps_view,
    format_memory_impact_preview_view,
    format_quality_gate_view,
    format_receipt_viewer,
    format_run_delta_view,
    format_work_graph_explorer,
)

NOW = datetime(2026, 5, 16, 17, 55, tzinfo=UTC)


def test_operator_views_reexports_artifact_formatters() -> None:
    from craik.runtime.companions import operator_artifact_views, operator_views
    from craik.runtime.memory import operator_memory_views

    assert (
        operator_views.format_contradiction_inbox
        is operator_artifact_views.format_contradiction_inbox
    )
    assert (
        operator_views.format_evidence_assumption_view
        is operator_artifact_views.format_evidence_assumption_view
    )
    assert (
        operator_views.format_receipt_viewer
        is operator_artifact_views.format_receipt_viewer
    )
    assert (
        operator_views.format_handoff_viewer
        is operator_artifact_views.format_handoff_viewer
    )
    assert (
        operator_views.format_work_graph_explorer
        is operator_artifact_views.format_work_graph_explorer
    )
    assert (
        operator_views.MemoryImpactPreviewSnapshot
        is operator_memory_views.MemoryImpactPreviewSnapshot
    )
    assert (
        operator_views.format_memory_impact_preview_view
        is operator_memory_views.format_memory_impact_preview_view
    )


def test_work_graph_explorer_formats_nodes_and_edges() -> None:
    export = WorkGraphExport(
        id="graph_task_docs_reconcile",
        task_id="task_docs_reconcile",
        nodes=[
            WorkGraphNode(
                id="task:task_docs_reconcile",
                type="task",
                label="Reconcile docs",
                task_id="task_docs_reconcile",
            ),
            WorkGraphNode(
                id="handoff:handoff_docs_reconcile",
                type="handoff",
                label="Docs handoff",
                task_id="task_docs_reconcile",
            ),
        ],
        edges=[
            WorkGraphEdge(
                id="edge:has_handoff",
                type="has_handoff",
                from_node="task:task_docs_reconcile",
                to_node="handoff:handoff_docs_reconcile",
                metadata={"status": "completed"},
            )
        ],
        created_at="2026-05-16T16:55:00Z",
    )
    lines = format_work_graph_explorer(export)

    assert lines[:4] == [
        "Work Graph: graph_task_docs_reconcile",
        "Task: task_docs_reconcile",
        "Nodes: 2",
        "Edges: 1",
    ]
    assert "- task:task_docs_reconcile [task] task=task_docs_reconcile:" in lines[6]
    assert "task:task_docs_reconcile -[has_handoff]-> handoff:handoff_docs_reconcile" in lines[-1]
    assert "status=completed" in lines[-1]


def test_work_graph_explorer_empty_state() -> None:
    export = WorkGraphExport(
        id="graph_all",
        task_id=None,
        nodes=[],
        edges=[],
        created_at="2026-05-16T16:55:00Z",
    )

    lines = format_work_graph_explorer(export)

    assert lines == [
        "Work Graph: graph_all",
        "Task: all",
        "Nodes: 0",
        "Edges: 0",
        "",
        "Nodes",
        "",
        "Edges",
    ]


def test_handoff_viewer_formats_summary_links_and_empty_sections() -> None:
    handoff = Handoff.model_validate(
        {
            "id": "handoff_docs_reconcile",
            "task_id": "task_docs_reconcile",
            "project_id": "project_stigmem",
            "agent": "agent:codex",
            "status": "completed",
            "summary": "Contract schema work completed with tests and docs.",
            "self_audit": {
                "schema_validated": True,
                "redaction_reviewed": True,
                "receipts_reviewed": True,
                "assumptions_reviewed": True,
                "validation_recorded": True,
                "policy_exceptions_disclosed": True,
                "notes": [],
            },
            "completed_actions": ["Added schemas.", "Validated fixtures."],
            "artifacts": ["docs/reference/schemas.md"],
            "files_changed": ["src/craik/contracts/models.py"],
            "risks": [],
            "next_steps": ["Implement project registry."],
            "receipt_ids": ["receipt_pytest"],
            "open_human_delegation_ids": ["delegation_docs_reconcile_approval"],
            "created_at": "2026-05-16T16:55:00Z",
        }
    )

    lines = format_handoff_viewer(handoff)

    assert lines[:6] == [
        "Handoff: handoff_docs_reconcile",
        "Task: task_docs_reconcile",
        "Project: project_stigmem",
        "Status: completed",
        "Agent: agent:codex",
        "Summary: Contract schema work completed with tests and docs.",
    ]
    assert "- receipt_pytest" in lines
    assert "- docs/reference/schemas.md" in lines
    assert "- src/craik/contracts/models.py" in lines
    assert "- none" in lines
    assert "- delegation_docs_reconcile_approval" in lines


def test_receipt_viewer_formats_capability_receipt_statuses() -> None:
    for status in ("passed", "failed", "denied", "skipped"):
        receipt = CapabilityReceipt.model_validate(
            {
                "id": f"receipt_{status}",
                "task_id": "task_docs_reconcile",
                "actor": "agent:codex",
                "capability": "shell.test",
                "target": "uv run --extra dev pytest",
                "policy_profile": "strict",
                "reason": "Validate operator receipt formatting.",
                "result": {
                    "status": status,
                    "summary": f"Receipt {status}.",
                    "metadata": {"redacted": True},
                },
                "redacted": True,
                "created_at": "2026-05-16T17:00:00Z",
            }
        )

        lines = format_receipt_viewer(receipt)

        assert f"Capability Receipt: receipt_{status}" in lines
        assert f"Status: {status}" in lines
        assert "Redacted: True" in lines


def test_receipt_viewer_formats_plugin_receipt_links() -> None:
    receipt = PluginReceipt.model_validate(
        {
            "id": "plugin_receipt_docs_reconcile",
            "task_id": "task_docs_reconcile",
            "actor": "agent:codex",
            "plugin_descriptor_id": "plugin_docs_reconcile",
            "action": "docs.reconcile",
            "capability_grant_ids": ["plugin_grant_docs_reconcile"],
            "trust_boundary": "project",
            "result": {
                "status": "denied",
                "summary": "Plugin action denied by policy.",
                "metadata": {"redacted": True},
            },
            "evidence_ids": ["evidence_readme_status"],
            "handoff_ids": ["handoff_docs_reconcile"],
            "redacted": True,
            "created_at": "2026-05-16T17:00:00Z",
        }
    )

    lines = format_receipt_viewer(receipt)

    assert "Plugin Receipt: plugin_receipt_docs_reconcile" in lines
    assert "Plugin: plugin_docs_reconcile" in lines
    assert "Probation: None" in lines
    assert "Status: denied" in lines
    assert "- plugin_grant_docs_reconcile" in lines
    assert "- evidence_readme_status" in lines
    assert "- handoff_docs_reconcile" in lines


def test_contradiction_inbox_formats_statuses_and_review_links() -> None:
    reports = [
        _contradiction("contradiction_open", "open"),
        _contradiction("contradiction_resolved", "resolved"),
        _contradiction("contradiction_ignored", "ignored", owner=None),
    ]

    lines = format_contradiction_inbox(reports)

    assert lines[0] == "Contradiction Inbox: 3"
    assert "- contradiction_ignored [ignored]" in lines
    assert "- contradiction_open [open]" in lines
    assert "- contradiction_resolved [resolved]" in lines
    assert "  Owner: unassigned" in lines
    assert "  Affected Artifacts: README.md" in lines
    assert "  Evidence: evidence_readme_status" in lines


def test_contradiction_inbox_empty_state() -> None:
    assert format_contradiction_inbox([]) == ["Contradiction Inbox: 0", "", "- none"]


def test_evidence_assumption_view_keeps_assumptions_distinct() -> None:
    evidence = EvidenceReference.model_validate(
        {
            "id": "evidence_readme_status",
            "source": "README.md",
            "kind": "file",
            "locator": "README.md#status",
            "summary": "README documents project status.",
            "captured_at": "2026-05-16T17:15:00Z",
        }
    )
    assumption = Assumption.model_validate(
        {
            "id": "assumption_docs_stale",
            "task_id": "task_docs_reconcile",
            "statement": "Docs may be stale.",
            "rationale": "Review requested docs reconciliation.",
            "evidence_ids": ["evidence_readme_status"],
            "confidence": 0.65,
            "status": "open",
        }
    )

    lines = format_evidence_assumption_view([evidence], [assumption])

    assert lines[0] == "Evidence: 1"
    assert "[file] source=README.md" in lines[2]
    assert "Assumptions: 1" in lines
    assert "[open] task=task_docs_reconcile confidence=0.65" in lines[-1]
    assert "evidence=evidence_readme_status" in lines[-1]


def test_evidence_assumption_view_empty_state() -> None:
    assert format_evidence_assumption_view([], []) == [
        "Evidence: 0",
        "",
        "- none",
        "",
        "Assumptions: 0",
        "",
        "- none",
    ]


def test_delegation_queue_formats_open_resolved_and_cancelled() -> None:
    delegations = [
        _delegation("delegation_open", "open", "approval"),
        _delegation("delegation_resolved", "resolved", "clarification", resolution="Approved."),
        _delegation("delegation_cancelled", "cancelled", "escalation", owner=None),
    ]

    lines = format_delegation_queue(delegations)

    assert lines[0] == "Delegation Queue: 3"
    assert "- delegation_cancelled [cancelled/escalation]" in lines
    assert "- delegation_open [open/approval]" in lines
    assert "- delegation_resolved [resolved/clarification]" in lines
    assert "  Owner: unassigned" in lines
    assert "  Policy: policy_docs_reconcile" in lines
    assert "  Receipts: receipt_pytest" in lines
    assert "  Resolution: Approved." in lines


def test_delegation_queue_empty_state() -> None:
    assert format_delegation_queue([]) == ["Delegation Queue: 0", "", "- none"]


def test_budget_quota_view_formats_configured_missing_and_exceeded_states() -> None:
    snapshot = BudgetQuotaSnapshot(
        configured_limits={"tokens": 1000, "requests": 25},
        usage={"tokens": 1200, "requests": 10},
        missing=["cost_usd"],
        exceeded=["tokens"],
        notes=["Cost data unavailable in local fixtures."],
    )

    lines = format_budget_quota_view(snapshot)

    assert lines[:3] == ["Budget And Quota", "", "Configured Limits"]
    assert "- requests: 25" in lines
    assert "- tokens: 1200" in lines
    assert "- cost_usd" in lines
    assert "- tokens" in lines
    assert "- Cost data unavailable in local fixtures." in lines


def test_budget_quota_view_empty_state_does_not_infer_costs() -> None:
    lines = format_budget_quota_view(BudgetQuotaSnapshot(missing=["cost_usd"]))

    assert lines.count("- none") == 4
    assert "- cost_usd" in lines


def test_instruction_distillation_view_formats_sources_proposals_and_reviews() -> None:
    source = InstructionSource.model_validate(
        {
            "id": "instruction_source_agents_md",
            "project_id": "project_craik",
            "kind": "agents_md",
            "path": "AGENTS.md",
            "owner": "team:platform",
            "trust_boundary": "repository",
            "active": True,
            "declared_by": "user:maintainer",
            "created_at": "2026-05-16T17:30:00Z",
        }
    )
    source_snapshot = InstructionSourceSnapshot.model_validate(
        {
            "id": "snapshot_agents_md",
            "project_id": "project_craik",
            "source_id": "instruction_source_agents_md",
            "path": "AGENTS.md",
            "content_hash": "abc123",
            "hash_status": "unchanged",
            "captured_at": "2026-05-16T17:31:00Z",
        }
    )
    provenance = InstructionProvenance.model_validate(
        {
            "id": "provenance_agents_review",
            "project_id": "project_craik",
            "source_id": "instruction_source_agents_md",
            "snapshot_id": "snapshot_agents_md",
            "path": "AGENTS.md",
            "start_line": 10,
            "end_line": 12,
            "summary": "Review instructions before promotion.",
            "captured_at": "2026-05-16T17:32:00Z",
        }
    )
    approved = DistilledInstructionProposal.model_validate(
        {
            "id": "proposal_review_before_promotion",
            "project_id": "project_craik",
            "source_id": "instruction_source_agents_md",
            "snapshot_id": "snapshot_agents_md",
            "category": "policy",
            "statement": "Review distilled instructions before promotion.",
            "rationale": "Instruction files are evidence, not automatic authority.",
            "confidence": 0.9,
            "provenance_ids": ["provenance_agents_review"],
            "evidence_ids": ["evidence_agents_md"],
            "promotion_status": "approved",
            "promoted_constraint_id": "constraint_review_before_promotion",
            "decided_by": "user:maintainer",
            "decided_at": "2026-05-16T17:35:00Z",
            "created_at": "2026-05-16T17:33:00Z",
        }
    )
    deferred = DistilledInstructionProposal.model_validate(
        {
            "id": "proposal_stale_instruction",
            "project_id": "project_craik",
            "source_id": "instruction_source_agents_md",
            "snapshot_id": "snapshot_agents_md",
            "category": "stale_risk",
            "statement": "Prior context may be stale after instruction changes.",
            "rationale": "Snapshot changed after extraction.",
            "confidence": 0.7,
            "provenance_ids": ["provenance_agents_review"],
            "promotion_status": "deferred",
            "decided_by": "user:maintainer",
            "decided_at": "2026-05-16T17:36:00Z",
            "created_at": "2026-05-16T17:34:00Z",
        }
    )
    review = InstructionPromotionReview.model_validate(
        {
            "id": "review_review_before_promotion",
            "project_id": "project_craik",
            "proposal_id": "proposal_review_before_promotion",
            "decision": "approved",
            "decided_by": "user:maintainer",
            "rationale": "Promotion keeps trust boundary explicit.",
            "promoted_constraint_id": "constraint_review_before_promotion",
            "policy_envelope_id": "policy_instruction_review",
            "receipt_ids": ["receipt_instruction_review"],
            "handoff_ids": ["handoff_instruction_review"],
            "created_at": "2026-05-16T17:37:00Z",
        }
    )

    lines = format_instruction_distillation_view(
        InstructionDistillationSnapshot(
            sources=[source],
            snapshots=[source_snapshot],
            provenance=[provenance],
            proposals=[deferred, approved],
            reviews=[review],
        )
    )

    assert lines[:3] == ["Instruction Distillation", "", "Sources"]
    assert (
        "- instruction_source_agents_md [agents_md/active] path=AGENTS.md "
        "owner=team:platform trust=repository"
    ) in lines
    assert any(
        line.startswith(
            "- snapshot_agents_md source=instruction_source_agents_md status=unchanged"
        )
        for line in lines
    )
    assert any(
        "range=L10-L12: Review instructions before promotion." in line for line in lines
    )
    assert "- proposal_review_before_promotion [approved/policy]" in lines
    assert "  Active Constraint: constraint_review_before_promotion" in lines
    assert "- proposal_stale_instruction [deferred/stale_risk]" in lines
    assert "  Active Constraint: none" in lines
    assert "- review_review_before_promotion [approved]" in lines[-7]
    assert "  Receipts: receipt_instruction_review" in lines
    assert "  Handoffs: handoff_instruction_review" in lines


def test_instruction_distillation_view_empty_state() -> None:
    lines = format_instruction_distillation_view(InstructionDistillationSnapshot())

    assert lines == [
        "Instruction Distillation",
        "",
        "Sources",
        "- none",
        "",
        "Snapshots",
        "- none",
        "",
        "Provenance",
        "- none",
        "",
        "Distilled Proposals",
        "- none",
        "",
        "Promotion Reviews",
        "- none",
    ]


def test_quality_gate_view_formats_score_bands_and_finding_statuses() -> None:
    handoff_score = HandoffQualityScore.model_validate(
        {
            "id": "handoff_quality_handoff_docs",
            "task_id": "task_quality",
            "project_id": "project_craik",
            "handoff_id": "handoff_docs",
            "score": 0.55,
            "band": "poor",
            "components": [
                {
                    "name": "summary",
                    "score": 0.8,
                    "weight": 0.2,
                    "rationale": "Summary is present.",
                },
                {
                    "name": "validation_records",
                    "score": 0.2,
                    "weight": 0.3,
                    "rationale": "Validation is missing.",
                },
            ],
            "blocking_reasons": ["missing validation records"],
            "created_at": "2026-05-16T17:40:00Z",
        }
    )
    evidence_score = EvidenceCoverageScore.model_validate(
        {
            "id": "evidence_coverage_handoff_docs",
            "task_id": "task_quality",
            "project_id": "project_craik",
            "handoff_id": "handoff_docs",
            "score": 0.72,
            "band": "adequate",
            "evidence_ids": ["receipt_pytest"],
            "required_evidence_ids": ["receipt_pytest", "receipt_mypy"],
            "missing_evidence_ids": ["receipt_mypy"],
            "weak_claims": [],
            "created_at": "2026-05-16T17:41:00Z",
        }
    )
    critic_finding = RuntimeCriticFinding.model_validate(
        {
            "id": "critic_missing_validation",
            "task_id": "task_quality",
            "project_id": "project_craik",
            "handoff_id": "handoff_docs",
            "finding_type": "missing_validation",
            "severity": "high",
            "summary": "Handoff claims tests passed without receipt links.",
            "rationale": "Quality gate requires validation evidence.",
            "affected_artifacts": ["handoff_docs"],
            "proposed_actions": ["Attach test receipt."],
            "review_status": "reviewable",
            "created_at": "2026-05-16T17:42:00Z",
        }
    )
    red_team_finding = RedTeamFinding.model_validate(
        {
            "id": "red_team_policy_bypass",
            "task_id": "task_quality",
            "project_id": "project_craik",
            "handoff_id": "handoff_docs",
            "finding_type": "policy_bypass",
            "severity": "critical",
            "summary": "Output bypasses required review.",
            "attack_path": "Skip handoff quality review before promotion.",
            "affected_artifacts": ["proposal_quality"],
            "evidence_ids": ["evidence_policy_review"],
            "proposed_actions": ["Require adjudication before promotion."],
            "blocking": True,
            "review_status": "reviewable",
            "created_at": "2026-05-16T17:43:00Z",
        }
    )

    lines = format_quality_gate_view(
        QualityGateSnapshot(
            handoff_scores=[handoff_score],
            evidence_scores=[evidence_score],
            critic_findings=[critic_finding],
            red_team_findings=[red_team_finding],
        )
    )

    assert lines[0] == "Quality Gate: blocked"
    assert "- handoff_quality_handoff_docs [poor] score=0.55 handoff=handoff_docs" in lines
    assert "  Blocking Reasons: missing validation records" in lines
    assert "summary=0.80" in next(line for line in lines if line.startswith("  Components:"))
    assert any(
        line.startswith("- evidence_coverage_handoff_docs [adequate] score=0.72")
        for line in lines
    )
    assert "  Missing Evidence: receipt_mypy" in lines
    assert "- critic_missing_validation [reviewable/high] type=missing_validation" in lines
    assert "  Authoritative: False" in lines
    assert (
        "- red_team_policy_bypass [reviewable/critical] type=policy_bypass blocking=True"
        in lines
    )
    assert "  Proposed Actions: Require adjudication before promotion." in lines


def test_quality_gate_view_clear_empty_state() -> None:
    assert format_quality_gate_view(QualityGateSnapshot()) == [
        "Quality Gate: clear",
        "",
        "Handoff Quality Scores",
        "- none",
        "",
        "Evidence Coverage Scores",
        "- none",
        "",
        "Critic Findings",
        "- none",
        "",
        "Red-Team Findings",
        "- none",
    ]


def test_memory_impact_preview_view_separates_proposals_from_facts() -> None:
    add_proposal = _memory_proposal(
        "memprop_add_docs",
        operation="add",
        value="Craik uses reviewable memory proposals.",
    )
    invalidation = _memory_proposal(
        "memprop_invalidate_docs",
        operation="invalidate",
        value="Craik writes durable facts directly.",
        evidence=False,
    )
    preview = MemoryImpactPreview.model_validate(
        {
            "id": "mempreview_task_docs",
            "task_id": "task_docs",
            "facts_to_add": [
                {
                    "entity": "repo:craik",
                    "relation": "craik:memory_policy",
                    "value": "Craik uses reviewable memory proposals.",
                    "source": "docs/guides/memory-proposals.md",
                    "scope": "local",
                    "trust_class": "observed",
                }
            ],
            "facts_to_invalidate": [
                {
                    "entity": "repo:craik",
                    "relation": "craik:memory_policy",
                    "value": "Craik writes durable facts directly.",
                    "source": "docs/old-memory.md",
                    "scope": "local",
                    "trust_class": "stale-risk",
                }
            ],
            "likely_contradictions": [
                {
                    "entity": "repo:craik",
                    "relation": "craik:memory_policy",
                    "existing_value": "Craik writes durable facts directly.",
                    "proposed_value": "Craik uses reviewable memory proposals.",
                    "reason": "Proposal updates an existing memory policy value.",
                }
            ],
            "evidence_missing": ["memprop_invalidate_docs"],
            "scope_summary": {"local": 2},
            "created_at": "2026-05-16T17:50:00Z",
        }
    )

    lines = format_memory_impact_preview_view(
        MemoryImpactPreviewSnapshot(
            preview=preview,
            proposals=[invalidation, add_proposal],
            policy_envelope_id="policy_memory_review",
            receipt_ids=["receipt_memory_preview"],
        )
    )

    assert lines[:6] == [
        "Memory Impact Preview: mempreview_task_docs",
        "Task: task_docs",
        "Policy: policy_memory_review",
        "Receipts: receipt_memory_preview",
        "",
        "Proposed Memory Writes",
    ]
    assert "- memprop_add_docs [pending/add]" in lines
    assert "- memprop_invalidate_docs [pending/invalidate]" in lines
    assert "  Evidence: none" in lines
    assert any(
        line.startswith(
            "- repo:craik craik:memory_policy='Craik uses reviewable memory proposals.'"
        )
        for line in lines
    )
    assert "- memprop_invalidate_docs" in lines
    assert "- repo:craik craik:memory_policy" in lines
    assert "  Existing: Craik writes durable facts directly." in lines
    assert "  Proposed: Craik uses reviewable memory proposals." in lines
    assert "- local: 2" in lines


def test_memory_impact_preview_view_empty_preview_sections() -> None:
    preview = MemoryImpactPreview.model_validate(
        {
            "id": "mempreview_task_empty",
            "task_id": "task_empty",
            "created_at": "2026-05-16T17:50:00Z",
        }
    )

    lines = format_memory_impact_preview_view(MemoryImpactPreviewSnapshot(preview=preview))

    assert lines[:6] == [
        "Memory Impact Preview: mempreview_task_empty",
        "Task: task_empty",
        "Policy: none",
        "Receipts: none",
        "",
        "Proposed Memory Writes",
    ]
    assert lines.count("- none") == 6


def test_memory_impact_preview_view_keeps_legacy_import_surface() -> None:
    from craik.runtime import operator_memory_views, operator_views

    assert (
        operator_views.format_memory_impact_preview_view
        is operator_memory_views.format_memory_impact_preview_view
    )
    assert (
        operator_views.MemoryImpactPreviewSnapshot
        is operator_memory_views.MemoryImpactPreviewSnapshot
    )


def test_known_traps_view_formats_active_expired_and_contradicted_states() -> None:
    active = _known_trap("trap_active", "active")
    expired = _known_trap(
        "trap_expired",
        "active",
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    contradicted = _known_trap(
        "trap_contradicted",
        "contradicted",
        contradiction_ids=["contradiction_trap"],
    )
    negative_active = _negative_knowledge("negative_active")
    negative_expired = _negative_knowledge(
        "negative_expired",
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    negative_contradicted = _negative_knowledge(
        "negative_contradicted",
        contradiction_ids=["contradiction_negative"],
    )

    lines = format_known_traps_view(
        KnownTrapsSnapshot(
            known_traps=[contradicted, expired, active],
            negative_knowledge=[negative_contradicted, negative_expired, negative_active],
            now=NOW,
        )
    )

    assert lines[:2] == ["Known Traps", ""]
    assert "- trap_active [active/tool]" in lines
    assert "- trap_expired [expired/tool]" in lines
    assert "- trap_contradicted [contradicted/tool]" in lines
    assert "  Project: project_traps" in lines
    assert "  Task: task_traps" in lines
    assert "  Avoidance: Refresh state before relying on it." in lines
    assert "  Evidence: evidence_trap" in lines
    assert "  Contradictions: contradiction_trap" in lines
    assert "- negative_active [active] scope=repository trust=observed" in lines
    assert "- negative_expired [expired] scope=repository trust=observed" in lines
    assert "- negative_contradicted [contradicted] scope=repository trust=observed" in lines


def test_known_traps_view_empty_state() -> None:
    assert format_known_traps_view(KnownTrapsSnapshot()) == [
        "Known Traps",
        "",
        "- none",
        "",
        "Negative Knowledge",
        "- none",
    ]


def test_knowledge_resolution_view_formats_receipt_provenance() -> None:
    debt = ContextDebtRecord(
        id="context_debt_docs",
        task_id="task_docs",
        kind="omitted_doc",
        status="resolved",
        summary="Docs were omitted.",
        created_at=NOW,
        resolved_at=NOW,
        resolved_by_receipt_id="receipt_context_debt",
    )
    unknown = UnknownRecord(
        id="unknown_docs",
        task_id="task_docs",
        status="resolved",
        question="Which docs prove this?",
        needed_resolution="repo_inspection",
        next_action="Read docs.",
        resolved_answer="README has the state.",
        created_at=NOW,
        resolved_at=NOW,
        resolved_by_receipt_id="receipt_missing",
    )
    request = ContextRequest(
        id="context_request_docs",
        task_id="task_docs",
        requester="operator-123",
        kind="repo_inspection",
        question="Need docs state.",
        needed_for="Release readiness.",
        created_at=NOW,
    )
    receipt = CapabilityReceipt(
        id="receipt_context_debt",
        task_id="task_docs",
        actor="operator-123",
        capability="context_debt.resolve",
        target="context_debt_docs",
        policy_profile="strict",
        reason="Resolved context debt.",
        result={"status": "passed", "summary": "Resolved context debt."},
        created_at=NOW,
    )

    lines = format_knowledge_resolution_view(
        KnowledgeResolutionSnapshot(
            context_debt=[debt],
            unknowns=[unknown],
            context_requests=[request],
            receipts=[receipt],
        )
    )

    assert "  Resolution Receipt: receipt_context_debt (verified)" in lines
    assert "  Resolution Receipt: receipt_missing (missing or tampered)" in lines
    assert "  Fulfillment Receipt: unresolved" in lines


def test_run_delta_view_formats_change_kinds_and_recovery_links() -> None:
    delta = RunDelta.model_validate(
        {
            "id": "rundelta_task_docs",
            "project_id": "project_craik",
            "task_id": "task_docs",
            "previous_handoff_id": "handoff_previous",
            "current_handoff_id": "handoff_current",
            "case_file_ids": ["case_docs"],
            "receipt_ids": ["receipt_pytest"],
            "contradiction_ids": ["contradiction_docs"],
            "active_instruction_constraint_ids": ["constraint_review"],
            "changes": [
                {
                    "kind": "created",
                    "entity_type": "receipt",
                    "entity_id": "receipt_pytest",
                    "summary": "Validation receipt was created.",
                    "current_ref": "receipt_pytest",
                    "evidence_ids": ["evidence_pytest"],
                },
                {
                    "kind": "updated",
                    "entity_type": "handoff",
                    "entity_id": "handoff_current",
                    "summary": "Current handoff replaced the previous one.",
                    "previous_ref": "handoff_previous",
                    "current_ref": "handoff_current",
                },
                {
                    "kind": "removed",
                    "entity_type": "contradiction",
                    "entity_id": "contradiction_old",
                    "summary": "Old contradiction is no longer open.",
                    "previous_ref": "contradiction_old",
                },
                {
                    "kind": "unchanged",
                    "entity_type": "case_file",
                    "entity_id": "case_docs",
                    "summary": "Case file remains usable.",
                    "previous_ref": "case_docs",
                    "current_ref": "case_docs",
                },
            ],
            "summary": "Run state changed since the previous handoff.",
            "created_at": "2026-05-16T18:00:00Z",
        }
    )
    recovery = RecoverySession.model_validate(
        {
            "id": "recovery_task_docs",
            "project_id": "project_craik",
            "task_id": "task_docs",
            "status": "changed_state",
            "run_delta_id": "rundelta_task_docs",
            "resume_summary": "Review changed handoff and contradiction state.",
            "required_actions": ["Review current handoff."],
            "stale_risks": ["Previous handoff may be stale."],
            "handoff_ids": ["handoff_current"],
            "case_file_ids": ["case_docs"],
            "receipt_ids": ["receipt_pytest"],
            "contradiction_ids": ["contradiction_docs"],
            "active_instruction_constraint_ids": ["constraint_review"],
            "created_at": "2026-05-16T18:01:00Z",
        }
    )

    lines = format_run_delta_view(RunDeltaSnapshot(delta=delta, recovery_sessions=[recovery]))

    assert lines[:6] == [
        "Run Delta: rundelta_task_docs",
        "Project: project_craik",
        "Task: task_docs",
        "Previous Handoff: handoff_previous",
        "Current Handoff: handoff_current",
        "Summary: Run state changed since the previous handoff.",
    ]
    assert "Created: 1" in lines
    assert "Updated: 1" in lines
    assert "Removed: 1" in lines
    assert "Unchanged: 1" in lines
    assert (
        "- receipt:receipt_pytest prev=none current=receipt_pytest "
        "evidence=evidence_pytest: Validation receipt was created."
    ) in lines
    assert (
        "- recovery_task_docs [changed_state] delta=rundelta_task_docs"
        in lines
    )
    assert "  Required Actions: Review current handoff." in lines
    assert "  Handoffs: handoff_current" in lines
    assert "  Active Instruction Constraints: constraint_review" in lines


def test_run_delta_view_empty_change_and_recovery_state() -> None:
    delta = RunDelta.model_validate(
        {
            "id": "rundelta_empty",
            "project_id": "project_craik",
            "summary": "No changes.",
            "created_at": "2026-05-16T18:00:00Z",
        }
    )

    lines = format_run_delta_view(RunDeltaSnapshot(delta=delta))

    assert lines[0] == "Run Delta: rundelta_empty"
    assert "Task: all" in lines
    assert "Changes" in lines
    assert "- none" in lines
    assert lines[-3:] == ["", "Recovery Sessions", "- none"]


def _delegation(
    delegation_id: str,
    status: str,
    kind: str,
    *,
    owner: str | None = "user:maintainer",
    resolution: str | None = None,
) -> HumanDelegationPoint:
    return HumanDelegationPoint.model_validate(
        {
            "id": delegation_id,
            "task_id": "task_docs_reconcile",
            "kind": kind,
            "status": status,
            "summary": "Human review required.",
            "requested_decision": "Approve fixture update.",
            "requested_by": "agent:codex",
            "owner": owner,
            "policy_envelope_id": "policy_docs_reconcile",
            "receipt_ids": ["receipt_pytest"],
            "created_at": "2026-05-16T17:20:00Z",
            "resolved_at": "2026-05-16T17:25:00Z" if resolution else None,
            "resolution": resolution,
        }
    )


def _known_trap(
    trap_id: str,
    status: str,
    *,
    created_at: datetime = NOW,
    expires_at: datetime | None = None,
    contradiction_ids: list[str] | None = None,
) -> KnownTrap:
    return KnownTrap.model_validate(
        {
            "id": trap_id,
            "project_id": "project_traps",
            "task_id": "task_traps",
            "kind": "tool",
            "status": status,
            "statement": "GitHub state can become stale during a run.",
            "avoidance": "Refresh state before relying on it.",
            "evidence_ids": ["evidence_trap"],
            "handoff_ids": ["handoff_traps"],
            "contradiction_ids": contradiction_ids or [],
            "created_at": created_at,
            "expires_at": expires_at,
        }
    )


def _negative_knowledge(
    knowledge_id: str,
    *,
    created_at: datetime = NOW,
    expires_at: datetime | None = None,
    contradiction_ids: list[str] | None = None,
) -> NegativeKnowledge:
    return NegativeKnowledge.model_validate(
        {
            "id": knowledge_id,
            "project_id": "project_traps",
            "task_id": "task_traps",
            "statement": "No browser dashboard exists in v0.7.0.",
            "scope": "repository",
            "trust_class": "observed",
            "evidence_ids": ["evidence_tree"],
            "handoff_ids": ["handoff_traps"],
            "contradiction_ids": contradiction_ids or [],
            "created_at": created_at,
            "expires_at": expires_at,
        }
    )


def _memory_proposal(
    proposal_id: str,
    *,
    operation: str,
    value: str,
    evidence: bool = True,
) -> MemoryProposal:
    return MemoryProposal.model_validate(
        {
            "id": proposal_id,
            "task_id": "task_docs",
            "run_id": "run_docs",
            "step_id": "step_memory",
            "handoff_id": "handoff_docs",
            "operation": operation,
            "fact": {
                "entity": "repo:craik",
                "relation": "craik:memory_policy",
                "value": value,
                "source": "docs/guides/memory-proposals.md",
                "confidence": 0.9,
                "scope": "local",
                "trust_class": "observed",
            },
            "evidence": [
                {
                    "id": "evidence_memory_docs",
                    "source": "docs/guides/memory-proposals.md",
                    "kind": "file",
                    "locator": "docs/guides/memory-proposals.md#promotion-rules",
                    "summary": "Memory proposals require review.",
                    "captured_at": "2026-05-16T17:49:00Z",
                }
            ]
            if evidence
            else [],
        }
    )


def _contradiction(
    report_id: str,
    status: str,
    *,
    owner: str | None = "user:maintainer",
) -> ContradictionReport:
    return ContradictionReport.model_validate(
        {
            "id": report_id,
            "task_id": "task_docs_reconcile",
            "facts": ["fact_docs_planned", "fact_cli_implemented"],
            "summary": "Docs and implementation disagree.",
            "affected_artifacts": ["README.md"],
            "evidence_ids": ["evidence_readme_status"],
            "proposed_resolution": "Update docs to match implementation.",
            "status": status,
            "owner": owner,
            "created_at": "2026-05-16T17:10:00Z",
        }
    )
