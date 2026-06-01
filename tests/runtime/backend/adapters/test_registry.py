"""Tests for `select_adapter` dispatch and the concrete adapter stubs."""

from __future__ import annotations

import pytest

from craik.runtime.backend.adapters import registry
from craik.runtime.backend.adapters.concrete import (
    AnthropicAPI,
    AnthropicCLI,
    GoogleAPI,
    GoogleCLI,
    OpenAIAPI,
    OpenAICLI,
)
from craik.runtime.backend.adapters.registry import select_adapter


def _ctx_env() -> dict[str, str]:
    return {}


def test_anthropic_cli_id_returns_anthropic_cli_instance() -> None:
    adapter = select_adapter("anthropic-cli", _ctx_env())

    assert isinstance(adapter, AnthropicCLI)
    assert adapter.vendor == "anthropic"
    assert adapter.surface == "cli"


@pytest.mark.parametrize(
    ("identifier", "expected_cls", "vendor", "surface"),
    [
        ("anthropic-cli", AnthropicCLI, "anthropic", "cli"),
        ("anthropic-api", AnthropicAPI, "anthropic", "api"),
        ("openai-cli", OpenAICLI, "openai", "cli"),
        ("openai-api", OpenAIAPI, "openai", "api"),
        ("google-cli", GoogleCLI, "google", "cli"),
        ("google-api", GoogleAPI, "google", "api"),
    ],
)
def test_all_six_ids_map_to_correct_class(
    identifier: str,
    expected_cls: type,
    vendor: str,
    surface: str,
) -> None:
    adapter = select_adapter(identifier, _ctx_env())

    assert isinstance(adapter, expected_cls)
    assert adapter.vendor == vendor
    assert adapter.surface == surface


def test_auto_resolves_to_anthropic_cli_when_marker_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "anthropic_uses_claude_cli_marker", lambda env: True)

    adapter = select_adapter("auto", _ctx_env())

    assert isinstance(adapter, AnthropicCLI)


def test_auto_resolves_to_anthropic_api_when_marker_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "anthropic_uses_claude_cli_marker", lambda env: False)

    adapter = select_adapter("auto", _ctx_env())

    assert isinstance(adapter, AnthropicAPI)


@pytest.mark.parametrize(
    "identifier",
    ["foo-bar", "anthropic", "anthropic-cli-extra", "", "provider", "claude-code"],
)
def test_unknown_identifier_raises_value_error(identifier: str) -> None:
    with pytest.raises(ValueError):
        select_adapter(identifier, _ctx_env())


def test_no_phase2_stubs_remain() -> None:
    # All six ids now resolve to real Phase-4 adapters; ``openai-cli`` was the
    # last stub and graduated to the real observe-only ``OpenAICLI`` in Task 4.6,
    # so the placeholder ``_NotImplementedAdapter`` base no longer exists.
    from craik.runtime.backend.adapters import concrete

    assert not hasattr(concrete, "_NotImplementedAdapter")
    for identifier in (
        "anthropic-cli",
        "anthropic-api",
        "openai-cli",
        "openai-api",
        "google-cli",
        "google-api",
    ):
        adapter = select_adapter(identifier, _ctx_env())
        # A real adapter exposes the graduated capability surface.
        assert hasattr(adapter, "supports_live_gating")
