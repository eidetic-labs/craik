from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]


def test_v0124_command_surface_walkthrough(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "CRAIK_HOME": str(tmp_path / "craik-home"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    script = """
import json
from craik.runtime.shell.slash_commands import dispatch_slash_command

env = dict(CRAIK_HOME=r'''{home}''')
help_clear = dispatch_slash_command("/help clear", env=env)
help_receipts = dispatch_slash_command("/help receipts", env=env)
clear = dispatch_slash_command("/clear", env=env)
receipts = dispatch_slash_command("/receipts", env=env)
print(json.dumps({{
    "help_clear": help_clear.text,
    "help_receipts": help_receipts.text,
    "clear": clear.text,
    "receipts_empty": receipts.empty_state_message,
    "receipts_remediation": receipts.empty_state_remediation,
}}, sort_keys=True))
""".format(home=env["CRAIK_HOME"])
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
    data = cast(dict[str, str | None], payload)

    assert "## /clear" in str(data["help_clear"])
    assert "Confirmation: required" in str(data["help_clear"])
    assert "/receipts [detail <receipt-id>]" in str(data["help_receipts"])
    assert "confirmation modal" in str(data["clear"])
    assert data["receipts_empty"] == "No receipts found."
