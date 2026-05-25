from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_oauth_callback_safety_guard_passes_current_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_oauth_callback_safety.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "passed" in result.stdout


def test_oauth_callback_safety_guard_rejects_unsafe_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", fixture / "scripts")
    oauth_dir = fixture / "src" / "craik" / "runtime" / "auth"
    sources_dir = oauth_dir / "sources"
    sources_dir.mkdir(parents=True)
    (oauth_dir / "oauth_loopback.py").write_text(
        """
from http.server import HTTPServer

state = "stored"
refresh_token = "stored"
server = HTTPServer(("0.0.0.0", 0), object)
if state == "expected":
    pass
verifier = "secret"
open("x", "w").write(verifier)
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/check_oauth_callback_safety.py"],
        cwd=fixture,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "HTTPServer must bind to literal 127.0.0.1" in result.stderr
    assert "hmac.compare_digest" in result.stderr
    assert "PKCE verifier" in result.stderr
    assert "refresh tokens must not be stored" in result.stderr
