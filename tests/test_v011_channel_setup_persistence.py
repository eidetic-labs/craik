import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_channel_setup_persists_all_adapter_artifacts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    _put_operator_session(home)

    result = runner.invoke(
        app,
        ["channels", "setup", "slack"],
        env={"CRAIK_HOME": str(home), "CRAIK_SLACK_BOT_TOKEN": "secret-token"},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0, result.output
    assert _single_json_payload(result.stdout)
    payload = json.loads(result.stdout)
    assert payload["persisted"] == {
        "adapter_contract_id": "channel_adapter_slack",
        "identity_pairing_id": "channel_pairing_slack",
        "allowlist_id": "allowlist_slack",
        "policy_envelope_id": "policy_channel_slack",
    }
    assert "secret-token" not in result.stdout

    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        assert store.get_channel_adapter_contract("channel_adapter_slack") is not None
        pairing = store.get_channel_identity_pairing("channel_pairing_slack")
        assert pairing is not None
        assert pairing.subject == "operator:test"
        assert pairing.policy_envelope_id == "policy_channel_slack"
        allowlist = store.get_channel_allowlist("allowlist_slack")
        assert allowlist is not None
        assert allowlist.default_action == "deny"
        policy = store.get_channel_policy_envelope("policy_channel_slack")
        assert policy is not None
        assert policy.required_operator is True
        assert policy.allowed_operator_subjects == ["operator:test"]
    finally:
        store.close()


def test_channel_doctor_reports_persisted_adapter_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ensure_craik_home({"CRAIK_HOME": str(home)})
    _put_operator_session(home)
    setup = runner.invoke(
        app,
        ["channels", "setup", "webchat"],
        env={"CRAIK_HOME": str(home), "CRAIK_WEBCHAT_TOKEN": "secret-token"},
    )
    assert setup.exception is None, setup.output
    assert setup.exit_code == 0, setup.output

    result = runner.invoke(
        app,
        ["channels", "doctor", "webchat"],
        env={"CRAIK_HOME": str(home), "CRAIK_WEBCHAT_TOKEN": "secret-token"},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0, result.output
    assert _single_json_payload(result.stdout)
    payload = json.loads(result.stdout)
    assert payload["persisted"] == {
        "adapter_contract": True,
        "identity_pairing": True,
        "allowlist": True,
        "policy_envelope": True,
    }


def _put_operator_session(home: Path) -> None:
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )


def _single_json_payload(stdout: str) -> bool:
    stripped = stdout.strip()
    return stripped.startswith(("{", "[")) and stripped.endswith(("}", "]"))
