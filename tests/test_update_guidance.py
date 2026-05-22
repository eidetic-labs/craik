import json

from typer.testing import CliRunner

from craik.cli import app, package_version
from craik.runtime.projects.update_guidance import update_guidance_payload

runner = CliRunner()


def test_update_guidance_payload_is_non_mutating() -> None:
    payload = update_guidance_payload(installed_version="1.2.3")

    assert payload["installed_version"] == "1.2.3"
    assert payload["self_update_supported"] is False
    assert payload["supported_python"] == ">=3.12"
    assert "Craik does not rewrite its own installation." in payload["boundaries"]


def test_update_command_prints_guidance() -> None:
    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["installed_version"] == package_version()
    assert payload["self_update_supported"] is False
    assert payload["compatibility"]["contracts"] == "0.1.0"
    assert any("craik doctor" in step for step in payload["steps"])


def test_update_check_sets_automation_mode() -> None:
    result = runner.invoke(app, ["update", "--check"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["mode"] == "check"
