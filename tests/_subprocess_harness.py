from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CraikRun:
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


class CraikSubprocess:
    """Run the real Typer CLI in a subprocess with isolated Craik state."""

    def __init__(self, tmp_path: Path, extra_env: dict[str, str] | None = None) -> None:
        self.home = tmp_path / "craik-home"
        self.env = {
            **os.environ,
            "CRAIK_HOME": str(self.home),
            "PYTHONPATH": str(ROOT / "src"),
        }
        if extra_env:
            self.env.update(extra_env)

    def run(
        self,
        *args: str,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> CraikRun:
        values = {**self.env, **(env or {})}
        result = subprocess.run(
            [sys.executable, "-c", "from craik.cli import app; app()", *args],
            cwd=ROOT,
            env=values,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        return CraikRun(
            args=tuple(args),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
