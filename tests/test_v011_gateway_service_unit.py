from pathlib import Path

import pytest

from craik.runtime.gateway import GatewayDaemonConfigError, default_gateway_config
from craik.runtime.paths import ensure_craik_home
from craik.runtime.services.gateway import install_gateway_service
from craik.runtime.store import LocalStore


def test_gateway_service_units_use_absolute_craik_executable(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    executable = tmp_path / "bin" / "craik"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_gateway_config(default_gateway_config(project_id="project_gateway"))
    finally:
        store.close()

    launchd = install_gateway_service(
        paths,
        target_platform="Darwin",
        executable_path=executable,
    )
    systemd = install_gateway_service(
        paths,
        target_platform="Linux",
        executable_path=executable,
    )

    assert f"<string>{executable}</string><string>gateway</string>" in launchd.content
    assert "<string>craik</string><string>gateway</string>" not in launchd.content
    assert f"ExecStart={executable} gateway start" in systemd.content
    assert "ExecStart=craik gateway start" not in systemd.content


def test_gateway_service_rejects_relative_executable_path(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_gateway_config(default_gateway_config(project_id="project_gateway"))
    finally:
        store.close()

    with pytest.raises(GatewayDaemonConfigError, match="executable path must be absolute"):
        install_gateway_service(paths, target_platform="Linux", executable_path="craik")
