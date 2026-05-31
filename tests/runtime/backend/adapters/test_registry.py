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


def test_stub_run_raises_not_implemented_naming_class() -> None:
    from craik.runtime.backend.adapters.base import RunContext

    adapter = select_adapter("openai-api", _ctx_env())
    ctx = RunContext(
        prompt="hi",
        env={},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )

    with pytest.raises(NotImplementedError, match="OpenAIAPI"):
        adapter.run(ctx)
