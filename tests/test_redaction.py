import re

from craik.runtime.policy.redaction import RedactionConfig, contains_unredacted_secret, redact


def test_redacts_bearer_header() -> None:
    result = redact("Authorization: Bearer redactionfixture123")

    assert result.value == "Authorization: Bearer [REDACTED]"
    assert result.redacted is True


def test_redacts_api_key_query_shape() -> None:
    result = redact("call service api_key=redactionfixture123")

    assert result.value == "call service api_key=[REDACTED]"
    assert result.redacted_paths == ("$",)


def test_redacts_secret_flag_command_shape() -> None:
    result = redact("tool run --token redactionfixture123 --name demo")

    assert result.value == "tool run --token [REDACTED] --name demo"
    assert result.redacted_paths == ("$",)


def test_redacts_github_classic_pat() -> None:
    token = _token("ghp_", "AbCdEf0123456789AbCdEf0123456789AbCdEf")

    result = redact(f"GITHUB_TOKEN={token}")

    assert result.value == "GITHUB_TOKEN=[REDACTED]"
    assert token not in result.value


def test_redacts_github_oauth_server_and_refresh_tokens() -> None:
    for token in (
        _token("gho_", "test1234567890abcdef"),
        _token("ghs_", "test1234567890abcdef"),
        _token("ghr_", "test1234567890abcdef"),
    ):
        result = redact(token)

        assert result.value == "[REDACTED]"


def test_redacts_github_fine_grained_pat() -> None:
    token = _token("github_pat_", "11ABCDEFG_82chars1234567890abcdef")

    result = redact(token)

    assert result.value == "[REDACTED]"


def test_redacts_hyphenated_provider_tokens_still_work() -> None:
    assert redact(_token("sk-", "test1234567890abcdef")).value == "[REDACTED]"
    assert redact(_token("xoxb-", "test1234567890abcdef")).value == "[REDACTED]"


def _token(prefix: str, body: str) -> str:
    return prefix + body


def test_redacts_auth_url_without_destroying_shape() -> None:
    result = redact("https://user:redactionfixture123@example.com/path")

    assert result.value == "https://[REDACTED]:[REDACTED]@example.com/path"


def test_redacts_token_only_git_remote_without_destroying_shape() -> None:
    result = redact("https://redactionfixture123@github.com/eidetic-labs/craik.git")

    assert result.value == "https://[REDACTED]@github.com/eidetic-labs/craik.git"


def test_redacts_secret_key_in_structured_payload() -> None:
    payload = {
        "result": {
            "metadata": {
                "api_token": "redaction-fixture-value",
                "status": "failed",
            }
        }
    }

    result = redact(payload)

    assert result.value["result"]["metadata"]["api_token"] == "[REDACTED]"
    assert result.value["result"]["metadata"]["status"] == "failed"
    assert result.redacted_paths == ("$.result.metadata.api_token",)


def test_preserves_already_redacted_values() -> None:
    result = redact({"api_token": "[REDACTED]"})

    assert result.value == {"api_token": "[REDACTED]"}
    assert result.redacted is False


def test_configurable_secret_patterns() -> None:
    config = RedactionConfig(patterns=(re.compile(r"custom-secret-[0-9]+"),))

    result = redact("value custom-secret-1234", config)

    assert result.value == "value [REDACTED]"


def test_detects_unredacted_secret_material() -> None:
    assert contains_unredacted_secret({"password": "redaction-fixture-value"})
    assert not contains_unredacted_secret({"password": "[REDACTED]"})


def test_context_budget_token_counts_are_not_secret_keys() -> None:
    assert not contains_unredacted_secret({"max_tokens": 24000, "estimated_tokens": 12})


def test_provider_token_budget_counts_are_not_secret_keys() -> None:
    assert not contains_unredacted_secret(
        {
            "provider_token_budget": 24000,
            "provider_tokens_used": 1500,
            "provider_token_budget_remaining": 22500,
        }
    )


def test_policy_credential_constraints_are_not_secret_keys() -> None:
    assert not contains_unredacted_secret(
        {
            "allowed_credential_kinds": ["secret-ref"],
            "allowed_credential_profiles": ["openai:prod-*"],
        }
    )


def test_receipt_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.capability_receipt",
        "result": {
            "summary": "Authorization: Bearer redactionfixture123",
            "metadata": {"request_id": "req_123"},
        },
    }

    result = redact(payload)

    assert result.value["result"]["summary"] == "Authorization: Bearer [REDACTED]"
    assert result.value["result"]["metadata"]["request_id"] == "req_123"


def test_handoff_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.handoff",
        "commands_run": ["curl https://user:redactionfixture123@example.com/path"],
        "summary": "completed",
    }

    result = redact(payload)

    assert result.value["commands_run"] == [
        "curl https://[REDACTED]:[REDACTED]@example.com/path"
    ]
    assert result.value["summary"] == "completed"


def test_case_file_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.case_file",
        "repo_state": {"remote": "https://user:redactionfixture123@example.com/repo.git"},
        "docs": ["README.md"],
    }

    result = redact(payload)

    assert result.value["repo_state"]["remote"] == (
        "https://[REDACTED]:[REDACTED]@example.com/repo.git"
    )
    assert result.value["docs"] == ["README.md"]


def test_memory_proposal_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.memory_proposal",
        "fact": {
            "entity": "repo:demo",
            "relation": "craik:note",
            "value": "token=redactionfixture123",
        },
    }

    result = redact(payload)

    assert result.value["fact"]["value"] == "token=[REDACTED]"


def test_multimodal_transcript_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.speech_to_text_result",
        "transcript": {
            "text": "Authorization: Bearer redactionfixture123",
            "metadata": {
                "private_transcript_metadata": "private speaker detail",
                "confidence_model": "fixture",
            },
        },
        "policy_envelope_id": "policy_voice",
        "evidence_ids": ["evidence_voice"],
        "receipt_ids": ["receipt_voice"],
    }

    result = redact(payload)

    assert result.value["transcript"]["text"] == "Authorization: Bearer [REDACTED]"
    assert result.value["policy_envelope_id"] == "policy_voice"
    assert result.value["evidence_ids"] == ["evidence_voice"]
    assert result.value["receipt_ids"] == ["receipt_voice"]


def test_multimodal_media_metadata_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.multimodal_artifact_reference",
        "locator": "artifact?token=redactionfixture123",
        "media_metadata": {
            "api_token": "redaction-fixture-value",
            "duration_ms": 2400,
            "codec": "wav",
        },
        "policy_envelope_id": "policy_voice",
        "evidence_ids": ["evidence_media"],
        "receipt_ids": ["receipt_media"],
    }

    result = redact(payload)

    assert result.value["locator"] == "artifact?token=[REDACTED]"
    assert result.value["media_metadata"]["api_token"] == "[REDACTED]"
    assert result.value["media_metadata"]["duration_ms"] == 2400
    assert result.value["media_metadata"]["codec"] == "wav"


def test_companion_state_shape_redaction_regression() -> None:
    payload = {
        "schema": "craik.companion_state",
        "last_viewed_task_id": "task_review",
        "notification": {
            "summary": "token=redactionfixture123",
            "receipt_id": "receipt_review",
        },
        "credentials": "private",
        "local_path": "/Users/example/private-state.json",
    }

    result = redact(payload)

    assert result.value["notification"]["summary"] == "token=[REDACTED]"
    assert result.value["credentials"] == "[REDACTED]"
    assert result.value["notification"]["receipt_id"] == "receipt_review"
    assert contains_unredacted_secret(payload)
