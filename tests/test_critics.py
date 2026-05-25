import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import RedTeamFinding, RuntimeCriticFinding
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.critics import (
    blocking_red_team_findings,
    render_critic_finding_markdown,
    reviewable_critic_findings,
)
from craik.runtime.store import LocalStore

runner = CliRunner()


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _put_operator_session(home: Path) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )


def _critic(**overrides: object) -> RuntimeCriticFinding:
    payload = {
        "id": "critic_missing_validation",
        "task_id": "task_quality",
        "project_id": "project_quality",
        "finding_type": "missing_validation",
        "severity": "high",
        "summary": "The handoff claims tests passed without a receipt.",
        "rationale": "Validation claims must be backed by observed receipts.",
        "affected_artifacts": ["handoff_quality"],
        "evidence_ids": ["evidence_handoff_quality"],
        "proposed_actions": ["Run the validation command and persist a receipt."],
        "created_at": "2026-05-16T08:45:00Z",
    }
    payload.update(overrides)
    return RuntimeCriticFinding.model_validate(payload)


def _red_team(**overrides: object) -> RedTeamFinding:
    payload = {
        "id": "red_team_policy_bypass",
        "task_id": "task_quality",
        "project_id": "project_quality",
        "finding_type": "policy_bypass",
        "severity": "critical",
        "summary": "A runner could bypass review by marking a risky memory write complete.",
        "attack_path": "Submit memory updates without review evidence.",
        "affected_artifacts": ["proposal_quality"],
        "evidence_ids": ["evidence_policy_quality"],
        "proposed_actions": ["Require adjudication before memory promotion."],
        "blocking": True,
        "created_at": "2026-05-16T08:46:00Z",
    }
    payload.update(overrides)
    return RedTeamFinding.model_validate(payload)


def test_runtime_critic_findings_are_reviewable_and_non_authoritative(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        finding = _critic()
        store.put_runtime_critic_finding(finding)

        assert finding.authoritative is False
        assert finding.review_status == "reviewable"
        assert reviewable_critic_findings(store, task_id="task_quality") == [finding]
        assert "Authoritative: false" in render_critic_finding_markdown(finding)
    finally:
        store.close()


def test_runtime_critic_high_severity_requires_actions() -> None:
    with pytest.raises(ValidationError, match="high-severity critic findings"):
        _critic(proposed_actions=[])


def test_evidence_related_critic_findings_require_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence-related critic findings"):
        _critic(finding_type="unsupported_claim", evidence_ids=[])


def test_red_team_blockers_are_reviewable_and_non_authoritative(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        finding = _red_team()
        store.put_red_team_finding(finding)

        assert finding.authoritative is False
        assert finding.review_status == "reviewable"
        assert finding.blocking is True
        assert blocking_red_team_findings(store, task_id="task_quality") == [finding]
    finally:
        store.close()


def test_red_team_blockers_require_high_severity_and_actions() -> None:
    with pytest.raises(ValidationError, match="blocking red-team findings must be high"):
        _red_team(severity="medium")

    with pytest.raises(ValidationError, match="blocking red-team findings require"):
        _red_team(proposed_actions=[])


def test_adjudicated_findings_require_adjudication_link() -> None:
    with pytest.raises(ValidationError, match="adjudicated critic findings"):
        _critic(review_status="adjudicated")

    with pytest.raises(ValidationError, match="adjudicated red-team findings"):
        _red_team(review_status="adjudicated")


def test_review_critic_cli_emits_single_command_result_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)

    result = runner.invoke(
        app,
        [
            "review",
            "critic",
            "task_quality",
            "--finding-type",
            "unsupported_claim",
            "--summary",
            "The handoff claims tests passed without a receipt.",
            "--rationale",
            "Validation claims must be backed by observed receipts.",
            "--severity",
            "high",
            "--evidence-id",
            "evidence_handoff_quality",
            "--proposed-action",
            "Run validation and persist a receipt.",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    payload = json.loads(result.stdout)
    assert payload["task_id"] == "task_quality"
    assert payload["finding_type"] == "unsupported_claim"
    assert payload["authoritative"] is False
    assert payload["review_status"] == "reviewable"


def test_review_red_team_cli_emits_single_command_result_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)

    result = runner.invoke(
        app,
        [
            "review",
            "red-team",
            "task_quality",
            "--finding-type",
            "policy_bypass",
            "--summary",
            "A runner could bypass review.",
            "--attack-path",
            "Submit memory updates without review evidence.",
            "--severity",
            "critical",
            "--blocking",
            "--proposed-action",
            "Require adjudication before promotion.",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    payload = json.loads(result.stdout)
    assert payload["task_id"] == "task_quality"
    assert payload["finding_type"] == "policy_bypass"
    assert payload["blocking"] is True
