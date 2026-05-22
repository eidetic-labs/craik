import os
from pathlib import Path

import pytest

from craik.runtime.auth.sources import (
    EnvVarSecretManager,
    FileSecretManager,
    SecretManager,
    SecretRefCredentialError,
    SecretRefCredentialSource,
)


def test_secret_ref_source_resolves_file_secret(tmp_path: Path) -> None:
    secret_file = tmp_path / "secrets" / "secret.txt"
    secret_file.parent.mkdir()
    secret_file.write_text("file-secret\n", encoding="utf-8")
    secret_file.chmod(0o600)
    source = SecretRefCredentialSource(
        ref="secret.txt",
        manager=FileSecretManager(secrets_root=secret_file.parent),
    )

    headers = source.headers_for("anthropic")

    assert headers == {
        "anthropic-version": "2023-06-01",
        "x-api-key": "file-secret",
    }
    assert source.status().status == "ok"
    assert "file-secret" not in str(source.status())


def test_secret_manager_protocol_default_raises_not_implemented() -> None:
    class IncompleteSecretManager(SecretManager):
        pass

    manager = IncompleteSecretManager()

    with pytest.raises(NotImplementedError):
        manager.resolve("secret-ref")


def test_secret_ref_source_resolves_env_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAIK_PROVIDER_SECRET", "env-secret")
    source = SecretRefCredentialSource(
        ref="CRAIK_PROVIDER_SECRET",
        manager=EnvVarSecretManager(),
    )

    headers = source.headers_for("chat_completions")

    assert headers == {"Authorization": "Bearer env-secret"}
    assert "env-secret" not in str(source.status())


def test_secret_ref_source_returns_gemini_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAIK_PROVIDER_SECRET", "env-secret")
    source = SecretRefCredentialSource(
        ref="CRAIK_PROVIDER_SECRET",
        manager=EnvVarSecretManager(),
    )

    headers = source.headers_for("gemini")

    assert headers == {"x-goog-api-key": "env-secret"}


def test_secret_ref_source_status_does_not_leak_missing_reference(tmp_path: Path) -> None:
    source = SecretRefCredentialSource(
        ref="missing-secret.txt",
        manager=FileSecretManager(secrets_root=tmp_path),
    )

    status = source.status()

    assert status.status == "rejected"
    assert status.detail == "secret reference could not be resolved"
    assert "missing-secret.txt" not in str(status)


def test_file_secret_manager_rejects_group_or_world_readable_file(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    secret_file.chmod(0o644)
    manager = FileSecretManager(secrets_root=tmp_path)

    with pytest.raises(SecretRefCredentialError, match="secret reference could not be resolved"):
        manager.resolve("secret.txt")


def test_file_secret_manager_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("file-secret\n", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "secret.txt"
    link.symlink_to(target)
    manager = FileSecretManager(secrets_root=tmp_path)

    with pytest.raises(SecretRefCredentialError, match="secret reference could not be resolved"):
        manager.resolve("secret.txt")


def test_file_secret_manager_rejects_traversal_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("file-secret\n", encoding="utf-8")
    outside.chmod(0o600)
    root = tmp_path / "secrets"
    root.mkdir()
    manager = FileSecretManager(secrets_root=root)

    with pytest.raises(SecretRefCredentialError, match="secret reference could not be resolved"):
        manager.resolve("../outside.txt")


def test_file_secret_manager_rejects_intermediate_symlink_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("file-secret\n", encoding="utf-8")
    secret.chmod(0o600)
    root = tmp_path / "secrets"
    root.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    manager = FileSecretManager(secrets_root=root)

    with pytest.raises(SecretRefCredentialError, match="secret reference could not be resolved"):
        manager.resolve("linked/secret.txt")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is not available")
def test_file_secret_manager_rejects_fifo(tmp_path: Path) -> None:
    fifo = tmp_path / "secret.pipe"
    os.mkfifo(fifo)
    manager = FileSecretManager(secrets_root=tmp_path)

    with pytest.raises(SecretRefCredentialError, match="secret reference could not be resolved"):
        manager.resolve("secret.pipe")
