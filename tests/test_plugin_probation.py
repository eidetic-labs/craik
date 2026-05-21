import pytest
from pydantic import ValidationError

from craik.contracts.models import PluginProbation
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _criterion(name: str = "security_review", passed: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "required": True,
        "passed": passed,
        "summary": "Review plugin security posture.",
        "evidence_ids": ["evidence_readme_status"],
    }


def _decision(decision: str) -> dict[str, object]:
    return {
        "decision": decision,
        "decided_by": "user:maintainer",
        "rationale": f"Fixture {decision} decision.",
        "evidence_ids": ["evidence_readme_status"],
        "decided_at": "2026-05-16T16:10:00Z",
    }


def _probation(**overrides: object) -> PluginProbation:
    payload = {
        "id": "plugin_probation_docs_reconcile",
        "plugin_descriptor_id": "plugin_docs_reconcile",
        "policy_envelope_id": "policy_docs_reconcile",
        "status": "probationary",
        "criteria": [_criterion()],
        "compatibility_check_ids": ["freshness_github_state"],
        "evidence_ids": ["evidence_readme_status"],
        "receipt_ids": ["receipt_runner_fixture"],
        "decision": None,
        "expires_at": "2026-06-16T16:10:00Z",
        "durable_trust_granted": False,
        "created_at": "2026-05-16T16:10:00Z",
    }
    payload.update(overrides)
    return PluginProbation.model_validate(payload)


def test_plugin_probation_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        probation = _probation()
        store.put_plugin_probation(probation)

        stored = store.get_plugin_probation(probation.id)
        assert stored is not None
        assert stored.receipt_hmac
        assert stored.model_copy(update={"receipt_hmac": None}) == probation
        assert store.list_plugin_probations() == [stored]
        assert probation.durable_trust_granted is False
    finally:
        store.close()


def test_probationary_plugins_do_not_receive_durable_trust() -> None:
    with pytest.raises(ValidationError, match="durable trust"):
        _probation(durable_trust_granted=True)

    with pytest.raises(ValidationError, match="must not include a decision"):
        _probation(decision=_decision("promote"))


def test_promoted_plugins_require_passed_criteria_and_compatibility() -> None:
    promoted = _probation(
        status="promoted",
        criteria=[_criterion(passed=True)],
        decision=_decision("promote"),
    )

    assert promoted.status == "promoted"

    trusted = _probation(
        status="promoted",
        criteria=[_criterion(passed=True)],
        decision=_decision("promote"),
        durable_trust_granted=True,
    )

    assert trusted.durable_trust_granted is True

    with pytest.raises(ValidationError, match="required criteria"):
        _probation(
            status="promoted",
            criteria=[_criterion(passed=False)],
            decision=_decision("promote"),
        )

    criterion_without_evidence = _criterion(passed=True)
    criterion_without_evidence["evidence_ids"] = []
    with pytest.raises(ValidationError, match="criteria require evidence"):
        _probation(
            status="promoted",
            criteria=[criterion_without_evidence],
            decision=_decision("promote"),
        )

    with pytest.raises(ValidationError, match="compatibility"):
        _probation(
            status="promoted",
            criteria=[_criterion(passed=True)],
            compatibility_check_ids=[],
            decision=_decision("promote"),
        )


def test_plugin_probation_decisions_require_evidence() -> None:
    decision = _decision("reject")
    decision["evidence_ids"] = []

    with pytest.raises(ValidationError):
        _probation(status="rejected", decision=decision)


def test_rejected_plugins_require_reject_decision() -> None:
    rejected = _probation(status="rejected", decision=_decision("reject"))

    assert rejected.status == "rejected"

    with pytest.raises(ValidationError, match="reject decision"):
        _probation(status="rejected", decision=_decision("promote"))


def test_expired_plugins_require_expire_decision_and_expiration() -> None:
    expired = _probation(status="expired", decision=_decision("expire"))

    assert expired.status == "expired"

    with pytest.raises(ValidationError, match="expire decision"):
        _probation(status="expired", decision=_decision("reject"))

    with pytest.raises(ValidationError, match="expires_at"):
        _probation(status="expired", decision=_decision("expire"), expires_at=None)
