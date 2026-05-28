"""Rust/Ratatui TUI launch discovery."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from os import X_OK, PathLike, access
from pathlib import Path


@dataclass(frozen=True)
class RatatuiRuntimeDiagnostics:
    """Resolved launch paths for the Rust/Ratatui TUI."""

    command: tuple[str, ...] | None
    installed_binary: str | None
    cargo: str | None
    manifest: str | None
    legacy_command: str = "craik tui-textual"

    def as_lines(self) -> tuple[str, ...]:
        command = " ".join(self.command) if self.command is not None else "unavailable"
        return (
            f"command: {command}",
            f"installed_binary: {self.installed_binary or 'not found'}",
            f"cargo: {self.cargo or 'not found'}",
            f"source_manifest: {self.manifest or 'not found'}",
            f"legacy_textual: {self.legacy_command}",
        )


def ratatui_command() -> list[str] | None:
    """Return the preferred command for launching the Rust/Ratatui TUI."""
    installed = shutil.which("craik-tui-rs")
    if installed is not None:
        return [installed]
    manifest = ratatui_manifest_path()
    if manifest is None:
        return None
    return ["cargo", "run", "--locked", "--manifest-path", str(manifest)]


def cargo_path() -> str | None:
    """Return Cargo from PATH or the standard rustup install location."""
    discovered = shutil.which("cargo")
    if discovered is not None:
        return discovered
    rustup_cargo = Path.home() / ".cargo" / "bin" / "cargo"
    return str(rustup_cargo) if _is_executable_file(rustup_cargo) else None


def ratatui_runtime_diagnostics() -> RatatuiRuntimeDiagnostics:
    """Return launch diagnostics for packaging and install guidance."""
    installed = shutil.which("craik-tui-rs")
    cargo = cargo_path()
    manifest = ratatui_manifest_path()
    command: tuple[str, ...] | None
    if installed is not None:
        command = (installed,)
    elif manifest is not None:
        command = ("cargo", "run", "--locked", "--manifest-path", str(manifest))
    else:
        command = None
    return RatatuiRuntimeDiagnostics(
        command=command,
        installed_binary=installed,
        cargo=cargo,
        manifest=str(manifest) if manifest is not None else None,
    )


def ratatui_runtime_error(message: str, diagnostics: RatatuiRuntimeDiagnostics) -> str:
    """Format a launch error with actionable runtime diagnostics."""
    detail = "\n".join(f"  - {line}" for line in diagnostics.as_lines())
    return f"{message}\nRust TUI diagnostics:\n{detail}"


def ratatui_manifest_path() -> Path | None:
    """Return the Rust TUI manifest path when running from a source checkout."""
    root = Path(__file__).resolve().parents[5]
    manifest = root / "crates" / "craik-tui-rs" / "Cargo.toml"
    return manifest if manifest.exists() else None


def _is_executable_file(path: str | PathLike[str]) -> bool:
    return Path(path).is_file() and access(path, X_OK)
