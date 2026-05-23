from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_terminal_ui_docs_describe_current_textual_runtime() -> None:
    content = (ROOT / "docs/guides/terminal-ui.md").read_text(encoding="utf-8")

    required = [
        "Use `craik` in an interactive terminal",
        "Textual TUI",
        "Status Bar",
        "/auth login [provider]",
        "/approvals decide <approval-id>",
        "CRAIK_HISTORY_MAX_ENTRIES=0",
        "CRAIK_NO_TUI=1",
    ]
    for phrase in required:
        assert phrase in content, f"terminal UI guide is missing {phrase!r}"


def test_privacy_docs_capture_data_flow_model() -> None:
    content = (ROOT / "docs/guides/privacy.md").read_text(encoding="utf-8")

    required = [
        "craik telemetry",
        "Third-party analytics",
        "Chat prompts",
        "Receipts, logs, and history",
        "CRAIK_HISTORY_MAX_ENTRIES=0",
    ]
    for phrase in required:
        assert phrase in content, f"privacy guide is missing {phrase!r}"


def test_privacy_guide_is_reachable_from_sidebars() -> None:
    content = (ROOT / "docs/sidebars.js").read_text(encoding="utf-8")

    assert content.count("'guides/privacy'") >= 2
