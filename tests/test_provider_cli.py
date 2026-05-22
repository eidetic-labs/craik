import json

from typer.testing import CliRunner

from craik.cli import app

runner = CliRunner()


def test_provider_list_prints_redacted_registry() -> None:
    result = runner.invoke(app, ["provider", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    providers = {item["id"]: item for item in payload}
    assert set(providers) >= {
        "provider_anthropic",
        "provider_fixture_local",
        "provider_local_ollama",
        "provider_openai",
    }
    assert providers["provider_fixture_local"]["secret_ref_names"] == [
        "CRAIK_PROVIDER_FIXTURE_TOKEN"
    ]
    assert providers["provider_openai"]["secret_ref_names"] == ["CRAIK_OPENAI_API_KEY"]
    assert "api_key" not in providers["provider_fixture_local"]["metadata"]
    assert providers["provider_local_ollama"]["secret_ref_names"] == []
    assert providers["provider_local_ollama"]["metadata"]["local_model_preset"] == "ollama"


def test_provider_show_prints_one_provider() -> None:
    result = runner.invoke(app, ["provider", "show", "provider_fixture_local"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "provider_fixture_local"
    assert payload["trust_boundary"] == "local"


def test_provider_show_prints_certified_openai_metadata() -> None:
    result = runner.invoke(app, ["provider", "show", "provider_openai"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "provider_openai"
    assert payload["provider"] == "openai"
    assert payload["trust_boundary"] == "third-party"
    assert payload["metadata"]["default_model"] == "gpt-5.2"


def test_provider_select_prints_policy_and_receipt_context() -> None:
    result = runner.invoke(
        app,
        [
            "provider",
            "select",
            "provider_fixture_local",
            "--mode",
            "runner",
            "--policy-envelope-id",
            "policy_provider",
            "--receipt-id",
            "receipt_provider_select",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["provider_id"] == "provider_fixture_local"
    assert payload["mode"] == "runner"
    assert payload["policy_envelope_id"] == "policy_provider"
    assert payload["receipt_ids"] == ["receipt_provider_select"]
    assert payload["redacted"] is True


def test_provider_select_rejects_unsupported_mode() -> None:
    result = runner.invoke(
        app,
        ["provider", "select", "provider_fixture_local", "--mode", "embedding"],
    )

    assert result.exit_code != 0
    assert "does not support mode" in result.output


def test_provider_local_presets_prints_no_secret_diagnostics() -> None:
    result = runner.invoke(app, ["provider", "local-presets"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    presets = {item["id"]: item for item in payload}
    assert {"openai-compatible", "ollama", "lm-studio", "vllm"} <= set(presets)
    assert presets["ollama"]["provider"]["secret_ref_names"] == []
    assert presets["ollama"]["provider"]["metadata"]["allow_local_base_url"] is True


def test_provider_local_health_rejects_unknown_preset() -> None:
    result = runner.invoke(app, ["provider", "local-health", "missing"])

    assert result.exit_code == 2
    assert "unknown local model preset" in result.output
