import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from craik.contracts.models import CapabilityReceipt, ReceiptResult, ToolResultAttestation
from craik.runtime.memory.freshness import (
    record_knowledge_freshness_probe,
    verify_tool_result_attestation,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.reviewing.critics import record_red_team_finding, record_runtime_critic_finding
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.handoffs import HandoffBlockedByExitDisciplineError, HandoffWriter
from craik.runtime.work.known_traps import record_known_trap, record_negative_knowledge
from craik.runtime.work.scratchpad import (
    fulfill_context_request,
    record_unknown,
    request_context,
    resolve_unknown,
    write_scratchpad_record,
)
from craik.runtime.work.tasks import create_task


def test_v0_5_capture_records_flow_into_case_handoff_and_quality(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Example")
        task = create_task(
            store,
            title="v0.5 capture",
            objective="Validate v0.5 capture pipeline.",
            project_id=project.id,
            mode="verify",
        )
        receipt = store.put_receipt(_receipt(task.id))
        write_scratchpad_record(
            store,
            task_id=task.id,
            project_id=project.id,
            owner="operator-123",
            note="Temporary finding from runtime review.",
            evidence_ids=[receipt.id],
        )
        unknown = record_unknown(
            store,
            task_id=task.id,
            project_id=project.id,
            owner="operator-123",
            question="Which acceptance test proves continuity?",
            needed_resolution="repo_inspection",
            next_action="Inspect the v0.5 e2e test.",
            evidence_ids=[receipt.id],
        )
        context_request = request_context(
            store,
            task_id=task.id,
            project_id=project.id,
            requester="operator-123",
            kind="repo_inspection",
            question="Confirm continuity records are in the case file.",
            needed_for="Release readiness.",
            unknown_id=unknown.id,
        )
        trap = record_known_trap(
            store,
            project_id=project.id,
            task_id=task.id,
            kind="workflow",
            statement="Closed issues are not release proof.",
            avoidance="Validate persisted artifacts before release.",
            evidence_ids=[receipt.id],
        )
        negative = record_negative_knowledge(
            store,
            project_id=project.id,
            task_id=task.id,
            statement="Release readiness has no external deployment proof yet.",
            scope="v0.5 release readiness",
            trust_class="observed",
            evidence_ids=[receipt.id],
        )
        contradicted_negative = record_negative_knowledge(
            store,
            project_id=project.id,
            task_id=task.id,
            statement="Issue closure alone is not feature completion.",
            scope="v0.5 release readiness",
            trust_class="observed",
            evidence_ids=[receipt.id],
            contradicted_fact="Closed milestone means release-ready.",
        )
        critic = record_runtime_critic_finding(
            store,
            task_id=task.id,
            project_id=project.id,
            finding_type="missing_validation",
            severity="high",
            summary="Capture layer needs an e2e test.",
            rationale="Contract-only tests did not exercise production writers.",
            proposed_actions=["Add v0.5 capture pipeline e2e coverage."],
        )
        red_team = record_red_team_finding(
            store,
            task_id=task.id,
            project_id=project.id,
            finding_type="policy_bypass",
            severity="high",
            summary="Exit could bypass unresolved context.",
            attack_path="Create a handoff while unknowns are still open.",
            proposed_actions=["Block handoff until unresolved context is resolved."],
            blocking=True,
        )
        store.put_tool_result_attestation(_attestation(task.id, project.id, receipt.id))
        attestation = store.get_tool_result_attestation("attestation_v0_5_capture")
        assert attestation is not None
        probe = record_knowledge_freshness_probe(
            store,
            task_id=task.id,
            project_id=project.id,
            target="repo status",
            kind="tool_result",
            trust_class="observed",
            observed_output_summary="Repo state was checked.",
            attestation_id=attestation.id,
            evidence_ids=[receipt.id],
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

        case_file = CaseFileAssembler(store).build(task.id)

        assert trap.id in case_file.context_budget["v0_5_continuity"]["known_trap_ids"]
        assert negative.id in case_file.context_budget["v0_5_continuity"]["negative_knowledge_ids"]
        assert store.get_contradiction(contradicted_negative.contradiction_ids[0]) is not None
        assert unknown.id in case_file.context_budget["v0_5_continuity"]["unknown_ids"]
        assert context_request.id in case_file.context_budget["v0_5_continuity"][
            "context_request_ids"
        ]
        assert probe.id in case_file.context_budget["v0_5_continuity"]["freshness_probe_ids"]
        assert critic.id == store.list_runtime_critic_findings()[0].id
        assert red_team.id == store.list_red_team_findings()[0].id
        assert attestation.receipt_hmac
        assert verify_tool_result_attestation(attestation, {"ok": True})

        try:
            HandoffWriter(store).create(
                task_id=task.id,
                agent="agent:test",
                summary="Attempted early exit.",
                tests_run=["pytest"],
                next_steps=["Resolve context."],
            )
        except HandoffBlockedByExitDisciplineError as error:
            assert "Open context requests remain" in str(error)
        else:  # pragma: no cover
            raise AssertionError("unresolved context should block handoff")

        resolve_unknown(
            store,
            unknown.id,
            answer="The v0.5 e2e test proves continuity.",
            resolved_by="operator-123",
        )
        fulfill_context_request(store, context_request.id, fulfilled_by="operator-123")
        handoff = HandoffWriter(store).create(
            task_id=task.id,
            agent="agent:test",
            summary="v0.5 capture pipeline validated.",
            completed_actions=["Captured and surfaced all v0.5 continuity records."],
            tests_run=["pytest tests/test_v0_5_0_pipeline_e2e.py"],
            next_steps=["Proceed to v0.5 pre-release checks."],
        )

        assert store.get_handoff_quality_score(f"handoff_quality_{handoff.id}") is not None
        assert store.get_evidence_coverage_score(f"evidence_coverage_{handoff.id}") is not None
    finally:
        store.close()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Example\n", encoding="utf-8")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        env={
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )


def _receipt(task_id: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        id="receipt_v0_5_capture",
        task_id=task_id,
        actor="agent:test",
        capability="test.capture",
        target="v0.5",
        policy_profile="strict",
        reason="Validate v0.5 capture.",
        result=ReceiptResult(status="passed", summary="Capture pipeline validated."),
        created_at=datetime.now(UTC),
    )


def _attestation(task_id: str, project_id: str, receipt_id: str) -> ToolResultAttestation:
    encoded = json.dumps({"ok": True}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ToolResultAttestation(
        id="attestation_v0_5_capture",
        task_id=task_id,
        project_id=project_id,
        tool_name="pytest",
        tool_identity="pytest",
        command="pytest tests/test_v0_5_0_pipeline_e2e.py",
        observed_output_summary="pytest passed",
        output_hash=hashlib.sha256(encoded).hexdigest(),
        trust_class="observed",
        evidence_ids=[receipt_id],
        receipt_id=receipt_id,
        captured_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
