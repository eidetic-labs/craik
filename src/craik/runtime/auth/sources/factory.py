"""Factory helpers for auth profile credential sources."""

from __future__ import annotations

import os
from pathlib import Path

from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialSource
from craik.runtime.auth.sources.api_key import EnvVarApiKeySource
from craik.runtime.auth.sources.cli_bridge import CLIBridgeCredentialSource
from craik.runtime.auth.sources.keyring_ref import KeyringRefCredentialSource
from craik.runtime.auth.sources.provider_oauth import ProviderOAuthCredentialSource
from craik.runtime.auth.sources.secret_ref import (
    EnvVarSecretManager,
    FileSecretManager,
    SecretRefCredentialSource,
)
from craik.runtime.auth.sources.stigmem_ref import StigmemCredentialSource


class AuthProfileSourceError(ValueError):
    """Raised when an auth profile cannot be mapped to a credential source."""


def source_for_auth_profile(profile: AuthProfile) -> CredentialSource:
    """Build the credential source configured by an auth profile."""
    if profile.kind is CredentialKind.API_KEY:
        env_var = profile.metadata.get("env_var")
        env_var = env_var if isinstance(env_var, str) else ""
        return EnvVarApiKeySource(env_var)
    if profile.kind is CredentialKind.OAUTH:
        return ProviderOAuthCredentialSource(profile)
    if profile.kind is CredentialKind.SECRET_REF:
        return _secret_ref_source(profile)
    if profile.kind is CredentialKind.KEYRING_REF:
        return _keyring_ref_source(profile)
    if profile.kind is CredentialKind.STIGMEM_REF:
        return _stigmem_ref_source(profile)
    if profile.kind is CredentialKind.CLI_BRIDGE:
        return _cli_bridge_source(profile)
    raise AuthProfileSourceError(f"unsupported auth profile kind/source: {profile.kind.value}")


def _secret_ref_source(profile: AuthProfile) -> SecretRefCredentialSource:
    ref = profile.metadata.get("ref")
    manager = profile.metadata.get("manager", "env")
    if not isinstance(ref, str):
        raise AuthProfileSourceError("secret-ref auth profile requires metadata.ref")
    secret_manager = (
        FileSecretManager(secrets_root=_secrets_root(profile))
        if manager == "file"
        else EnvVarSecretManager()
    )
    return SecretRefCredentialSource(ref=ref, manager=secret_manager)


def _keyring_ref_source(profile: AuthProfile) -> KeyringRefCredentialSource:
    ref = profile.metadata.get("ref")
    if not isinstance(ref, str):
        raise AuthProfileSourceError("keyring-ref auth profile requires metadata.ref")
    return KeyringRefCredentialSource(ref=ref)


def _secrets_root(profile: AuthProfile) -> Path:
    configured = profile.metadata.get("secrets_root")
    if isinstance(configured, str) and configured:
        return Path(configured)
    env_root = os.environ.get("CRAIK_SECRETS_ROOT")
    if env_root:
        return Path(env_root)
    craik_home = os.environ.get("CRAIK_HOME")
    if craik_home:
        return Path(craik_home) / "secrets"
    return Path("~/.craik/secrets")


def _stigmem_ref_source(profile: AuthProfile) -> StigmemCredentialSource:
    node_url = profile.metadata.get("node_url")
    entity = profile.metadata.get("entity")
    api_key = profile.metadata.get("api_key")
    scope = profile.metadata.get("scope", "team")
    relation = profile.metadata.get("relation", "craik:credential:value")
    timeout_seconds = profile.metadata.get("timeout_seconds", 5.0)
    if not isinstance(node_url, str) or not node_url:
        raise AuthProfileSourceError("stigmem-ref auth profile requires metadata.node_url")
    if not isinstance(entity, str) or not entity:
        raise AuthProfileSourceError("stigmem-ref auth profile requires metadata.entity")
    if scope not in {"local", "team", "company", "public"}:
        raise AuthProfileSourceError("stigmem-ref auth profile has unsupported scope")
    if not isinstance(relation, str) or not relation:
        raise AuthProfileSourceError("stigmem-ref auth profile requires metadata.relation")
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError):
        timeout = 5.0
    return StigmemCredentialSource.from_config(
        node_url=node_url,
        entity=entity,
        api_key=api_key if isinstance(api_key, str) else None,
        scope=scope,
        relation=relation,
        timeout_seconds=timeout,
    )


def _cli_bridge_source(profile: AuthProfile) -> CLIBridgeCredentialSource:
    command = profile.metadata.get("command")
    extractor = profile.metadata.get("token_extractor", "stdout_json")
    key_path = profile.metadata.get("key_path", ["token"])
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise AuthProfileSourceError("cli-bridge auth profile requires metadata.command")
    if extractor not in {"stdout_json", "stdout_line", "credentials_file"}:
        raise AuthProfileSourceError("cli-bridge auth profile has unsupported token_extractor")
    path = profile.metadata.get("credentials_file_path")
    return CLIBridgeCredentialSource(
        command=tuple(command),
        token_extractor=extractor,
        key_path=tuple(item for item in key_path if isinstance(item, str))
        if isinstance(key_path, list)
        else ("token",),
        credentials_file_path=Path(path) if isinstance(path, str) else None,
    )
