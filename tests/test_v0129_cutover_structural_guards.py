"""Regression tests for v0.12.9 cutover structural guards."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_legacy_modal_push_guard_allows_current_tree() -> None:
    guard = _load_script("check_no_legacy_modal_pushes")

    assert guard.scan_root(ROOT) == []


def test_legacy_modal_push_guard_detects_legacy_import_and_push(tmp_path: Path) -> None:
    guard = _load_script("check_no_legacy_modal_pushes")
    source = tmp_path / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
    _write(
        source,
        """
from craik.runtime.shell.textual_modals import AuthCaptureModal


def mount(app):
    app.push_screen(AuthCaptureModal())
""",
    )

    findings = guard.scan_root(tmp_path)

    assert any("imports legacy modal module" in finding for finding in findings)
    assert any("pushes a legacy modal" in finding for finding in findings)


def test_slash_command_specs_guard_allows_current_tree() -> None:
    guard = _load_script("check_no_slash_command_specs_consumption")

    assert guard.scan_root(ROOT) == []


def test_slash_command_specs_guard_detects_legacy_consumption(tmp_path: Path) -> None:
    guard = _load_script("check_no_slash_command_specs_consumption")
    source = tmp_path / "src" / "craik" / "runtime" / "shell" / "consumer.py"
    _write(
        source,
        """
from craik.runtime.shell.slash_command_schema import slash_command_specs


VALUES = slash_command_specs()
""",
    )

    findings = guard.scan_root(tmp_path)

    assert any("imports legacy slash-command specs API" in finding for finding in findings)
    assert any("consumes legacy slash-command specs API" in finding for finding in findings)


def test_interactive_prompts_guard_allows_current_dispatch() -> None:
    guard = _load_script("check_interactive_prompts_runtime_consumed")

    assert guard.validate_dispatch(ROOT / "src/craik/runtime/contract/dispatch.py") == []
    assert guard.validate_shell_callers(ROOT) == []


def test_interactive_prompts_guard_requires_intercept_around_callback(tmp_path: Path) -> None:
    guard = _load_script("check_interactive_prompts_runtime_consumed")
    dispatch = tmp_path / "dispatch.py"
    _write(
        dispatch,
        """
from contextlib import contextmanager


def invoke_slash_command():
    result = _call_entry()
    with intercept_interactive_prompts():
        pass
    return result


@contextmanager
def intercept_interactive_prompts():
    yield


def _call_entry():
    return None
""",
    )

    findings = guard.validate_dispatch(dispatch)

    assert any("does not wrap `_call_entry`" in finding for finding in findings)


def test_interactive_prompts_guard_requires_shell_prompt_handler(tmp_path: Path) -> None:
    guard = _load_script("check_interactive_prompts_runtime_consumed")
    source = tmp_path / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
    _write(
        source,
        """
from craik.runtime.contract.dispatch import invoke_slash_command as _contract_invoke


def dispatch(text, registry, env):
    return _contract_invoke(text, registry=registry, env=env)
""",
    )

    findings = guard.validate_shell_callers(tmp_path)

    assert any("non-None interactive_prompt_handler" in finding for finding in findings)


def test_interactive_prompts_guard_accepts_shell_prompt_handler(tmp_path: Path) -> None:
    guard = _load_script("check_interactive_prompts_runtime_consumed")
    source = tmp_path / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
    _write(
        source,
        """
from craik.runtime.contract.dispatch import invoke_slash_command as _contract_invoke


def dispatch(text, registry, env, handler):
    return _contract_invoke(
        text,
        registry=registry,
        env=env,
        interactive_prompt_handler=handler,
    )
""",
    )

    assert guard.validate_shell_callers(tmp_path) == []
