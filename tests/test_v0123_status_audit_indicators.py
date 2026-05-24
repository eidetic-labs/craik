from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from craik.contracts.models import PolicyEnvelope
from craik.runtime.auth.usage import (
    ProviderQuotaStatus,
    TokenUsageStatus,
    hidden_quota_status,
    quota_status_from_headers,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.envelope import is_auto_approve_shape
from craik.runtime.providers.provider_config import OPENAI_OFFICIAL_DOCS, ProviderRuntimeConfig
from craik.runtime.providers.provider_models import (
    ProviderMessage,
    ProviderRuntimeAdapter,
    ProviderRuntimeRequest,
    ProviderRuntimeResult,
)
from craik.runtime.providers.provider_runtime_support import provider_runtime_receipt
from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.store import LocalStore


def _report(tmp_path: Path) -> ReadinessReport:
    return ReadinessReport(
        state="fully-ready",
        home=tmp_path / ".craik",
        initialized=True,
        operator_required=True,
        operator_authenticated=True,
        provider_configured=True,
        local_model_configured=False,
        active_profile="default",
        active_model="openai/gpt-4o-mini",
    )


def test_token_usage_status_thresholds_and_display() -> None:
    assert TokenUsageStatus(49, 100).tier == "green"
    assert TokenUsageStatus(50, 100).tier == "yellow"
    assert TokenUsageStatus(80, 100).tier == "orange"
    assert TokenUsageStatus(95, 100).tier == "red"
    assert TokenUsageStatus(12_400, 200_000).display == "12.4K/200K"


def test_quota_status_hides_unavailable_provider_data() -> None:
    hidden = hidden_quota_status("provider endpoint unavailable")
    visible = ProviderQuotaStatus(remaining_percent=87)
    unauthorized = quota_status_from_headers(
        status_code=401,
        headers={"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "99"},
    )
    from_headers = quota_status_from_headers(
        status_code=200,
        headers={"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "17"},
    )

    assert hidden.available is False
    assert hidden.tier == "unknown"
    assert unauthorized.available is False
    assert visible.available is True
    assert visible.display == "87% quota"
    assert visible.tier == "green"
    assert from_headers.remaining_percent == 17
    assert from_headers.tier == "orange"


def test_status_bar_renders_token_quota_and_auto_approve_indicators(tmp_path: Path) -> None:
    bar = StatusBar()

    bar.update_status(
        _report(tmp_path),
        cwd=tmp_path,
        token_usage=TokenUsageStatus(170_000, 200_000),
        quota=ProviderQuotaStatus(remaining_percent=17),
        auto_approve=True,
    )

    assert "170K/200K" in bar.current_status
    assert "17% quota" in bar.current_status
    assert "auto-approve" in bar.current_status


def test_status_payload_warns_when_policy_auto_approves_capabilities(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_policy_envelope(
            PolicyEnvelope(
                id="policy_auto_all",
                task_id="task_auto_all",
                actor="agent:test",
                profile="custom",
                allowed_capabilities=["*"],
                approval_required=[],
            )
        )
    finally:
        store.close()

    payload = json.loads(dispatch_slash_command("/status", env=env).text)

    assert payload["auto_approve"]["active"] is True
    assert payload["auto_approve"]["policy_id"] == "policy_auto_all"
    assert "operator review" in payload["auto_approve"]["detail"]


def test_approve_all_capabilities_overrides_required_list() -> None:
    envelope = {
        "approve_all_capabilities": True,
        "required_approval_capabilities": ["sensitive.op"],
    }

    assert is_auto_approve_shape(envelope) is True


def test_provider_runtime_receipt_preserves_usage_metadata() -> None:
    class _Adapter:
        config = ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-4o-mini",
            secret_ref_name="OPENAI_API_KEY",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )

        def build_payload(self, request: ProviderRuntimeRequest) -> dict[str, object]:
            return {"messages": [message.model_dump() for message in request.messages]}

    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hello")],
    )
    result = ProviderRuntimeResult(
        provider_id="provider_openai",
        provider_family="openai",
        model="gpt-4o-mini",
        text="hello",
        usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    )

    receipt = provider_runtime_receipt(
        adapter=cast(ProviderRuntimeAdapter, _Adapter()),
        request=request,
        result=result,
        task_id="task_usage",
        policy_envelope_id="policy_usage",
        receipt_id="receipt_usage",
        actor="agent:test",
    )

    assert receipt.result.metadata["usage"] == {"input": 3, "output": 2, "total": 5}
