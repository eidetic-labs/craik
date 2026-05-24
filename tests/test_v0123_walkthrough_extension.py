from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from _subprocess_harness import CraikSubprocess

ROOT = Path(__file__).resolve().parents[1]


def _run_python_walkthrough(tmp_path: Path) -> dict[str, str | int]:
    env = {
        **os.environ,
        "CRAIK_HOME": str(tmp_path / "craik-home"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    script = """
import json
import sys
from craik.runtime.sandbox.mcp_discovery import render_mcp_discovery
from craik.runtime.shell.shell_invocation import run_shell_invocation
from craik.runtime.shell.slash_commands import dispatch_slash_command

env = dict(CRAIK_HOME=r'''{home}''')
rename = dispatch_slash_command("/rename Desk review", env=env)
theme = dispatch_slash_command("/theme monochrome", env=env)
mcp, mcp_code = render_mcp_discovery([], env=env)
shell = run_shell_invocation(
    "! " + sys.executable + " -c \\"print('walkthrough')\\"",
    env=env,
    cwd=r'''{cwd}''',
)
print(json.dumps({{
    "rename": rename.text,
    "theme": theme.text,
    "mcp": mcp,
    "mcp_code": mcp_code,
    "shell_exit": shell.exit_code,
    "shell_output": shell.stdout_preview.strip(),
    "shell_receipt": shell.receipt_id,
}}, sort_keys=True))
""".format(home=env["CRAIK_HOME"], cwd=ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, str | int], payload)


def test_v0123_interactive_walkthrough_surfaces(tmp_path: Path) -> None:
    cli = CraikSubprocess(tmp_path)

    mistype = cli.run("udpate")
    payload = _run_python_walkthrough(tmp_path)

    assert mistype.exit_code == 2
    assert "Did you mean 'craik update'?" in mistype.output
    assert payload["rename"] == "Shell session renamed to `Desk review`."
    assert payload["theme"] == "Theme set to `monochrome`."
    assert "No MCP clients configured" in str(payload["mcp"])
    assert payload["mcp_code"] == 0
    assert payload["shell_exit"] == 0
    assert payload["shell_output"] == "walkthrough"
    assert str(payload["shell_receipt"]).startswith("shell_invocation_")
