"""Per-vendor operator-runtime smoke: replay captured gateway streams and assert
the typed event contract holds per surface. This is the gate whose absence let
the receipt-without-run_id / no-model-output bug chain ship (Phase 7.3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from craik.runtime.backend.event_contract import validate_gateway_event

FIXTURES = Path("tests/fixtures/gateway")

SMOKE_MATRIX = [
    ("anthropic_cli_live_run.jsonl", "anthropic", "cli"),
    ("google_cli_live_run.jsonl", "google", "cli"),
    ("provider_anthropic_messages_stream.jsonl", "anthropic", "api"),
    ("provider_gemini_stream.jsonl", "google", "api"),
    ("provider_openai_responses_stream.jsonl", "openai", "api"),
]


def _load(name: str) -> list[dict]:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize("name,vendor,surface", SMOKE_MATRIX)
def test_smoke_fixture_satisfies_event_contract(name, vendor, surface):
    events = _load(name)
    assert events, f"{name} is empty"
    for index, ev in enumerate(events):
        # validate_gateway_event returns a list of contract issues ([] == valid);
        # it does NOT raise. Assert empty so a malformed event actually fails.
        issues = validate_gateway_event(ev, event_index=index)
        assert issues == [], f"{name}: contract issues at event {index}: {issues}"


@pytest.mark.parametrize("name,vendor,surface", SMOKE_MATRIX)
def test_smoke_receipts_always_carry_run_id(name, vendor, surface):
    for ev in _load(name):
        if ev.get("type") == "receipt.created":
            assert ev.get("run_id"), f"{name}: receipt.created missing run_id"
            assert ev.get("data", {}).get("receipt_id"), f"{name}: missing receipt_id"
