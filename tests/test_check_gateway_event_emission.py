import subprocess
import sys


def test_guard_passes_on_current_tree():
    r = subprocess.run([sys.executable, "scripts/check_gateway_event_emission.py"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
