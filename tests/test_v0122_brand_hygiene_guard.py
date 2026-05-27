from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_codebase_brand_hygiene.py"
_SPEC = importlib.util.spec_from_file_location("check_codebase_brand_hygiene", _SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
brand_hygiene = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = brand_hygiene
_SPEC.loader.exec_module(brand_hygiene)


def _write_clean_tree(root: Path) -> None:
    src = root / "src" / "craik"
    widgets = src / "runtime" / "shell" / "textual_widgets"
    tests = root / "tests"
    docs = root / "docs"
    scripts = root / "scripts"
    for path in (src, widgets, tests, docs, scripts):
        path.mkdir(parents=True)
    (scripts / "_brand_hygiene_allowlist.txt").write_text(
        "# path:line | reason: ...\n",
        encoding="utf-8",
    )
    (src / "runtime.py").write_text(
        'MESSAGE = "persistent bottom status bar"\n',
        encoding="utf-8",
    )
    (widgets / "glyph_palette.py").write_text(
        'STATE_INFLIGHT = "●"\n',
        encoding="utf-8",
    )
    (widgets / "status_bar.py").write_text(
        "from .glyph_palette import STATE_INFLIGHT\n",
        encoding="utf-8",
    )
    (tests / "test_runtime.py").write_text(
        'def test_runtime():\n    assert "openai"\n',
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        "Use product-functional language in public docs.\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Craik\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (root / "SECURITY.md").write_text("# Security\n", encoding="utf-8")


def test_brand_hygiene_guard_accepts_clean_tree(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == []


def test_brand_hygiene_guard_reports_forbidden_reference(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    forbidden = "Codex" + " CLI"
    (tmp_path / "src" / "craik" / "runtime.py").write_text(
        textwrap.dedent(
            f'''
            def render():
                """Matches the {forbidden} display shape."""
            '''
        ),
        encoding="utf-8",
    )

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == [
        "src/craik/runtime.py:3: forbidden brand reference "
        f"{forbidden!r} (private comparison reference)"
    ]


def test_brand_hygiene_guard_allows_runtime_contract_reference(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    runtime_name = "Claude" + " Code"
    (tmp_path / "docs" / "guide.md").write_text(
        f"Craik can delegate audited runs to the local {runtime_name} runtime.\n",
        encoding="utf-8",
    )

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == []


def test_brand_hygiene_guard_allows_documented_exception(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    forbidden = "Chat" + "GPT"
    (tmp_path / "docs" / "guide.md").write_text(
        f"Allowed historical note mentions {forbidden} here.\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "_brand_hygiene_allowlist.txt").write_text(
        "docs/guide.md:1 | reason: historical migration note retained for audit\n",
        encoding="utf-8",
    )

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == []


def test_brand_hygiene_guard_requires_allowlist_rationale(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    (tmp_path / "scripts" / "_brand_hygiene_allowlist.txt").write_text(
        "docs/guide.md:1\n",
        encoding="utf-8",
    )

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == [
        "scripts/_brand_hygiene_allowlist.txt: docs/guide.md:1:0 "
        "is missing a rationale"
    ]


def test_brand_hygiene_guard_enforces_allowlist_cap(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    entries = [
        f"docs/guide.md:{line} | reason: documented exception {line}"
        for line in range(1, brand_hygiene.ALLOWLIST_CAP + 2)
    ]
    (tmp_path / "scripts" / "_brand_hygiene_allowlist.txt").write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
    )

    failures = brand_hygiene.codebase_brand_hygiene_failures(tmp_path)

    assert failures == [
        "scripts/_brand_hygiene_allowlist.txt: allowlist has 6 entries; cap is 5"
    ]


def test_brand_hygiene_guard_rejects_raw_widget_glyphs(tmp_path: Path) -> None:
    _write_clean_tree(tmp_path)
    widget = (
        tmp_path
        / "src"
        / "craik"
        / "runtime"
        / "shell"
        / "textual_widgets"
        / "status_bar.py"
    )
    widget.write_text('STATUS = "● ready"\n', encoding="utf-8")

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == [
        "src/craik/runtime/shell/textual_widgets/status_bar.py:1: "
        "raw TUI glyph '●'; import from glyph_palette.py"
    ]
