import subprocess
import sys


def test_mode_passthrough_guard_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_vendor_mode_passthrough.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
