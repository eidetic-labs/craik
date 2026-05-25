"""Built-in credential sources."""

from craik.runtime.auth.sources.api_key import EnvVarApiKeySource
from craik.runtime.auth.sources.cli_bridge import (
    CLIBridgeCredentialError,
    CLIBridgeCredentialSource,
)
from craik.runtime.auth.sources.factory import AuthProfileSourceError, source_for_auth_profile
from craik.runtime.auth.sources.keyring_ref import KeyringRefCredentialSource
from craik.runtime.auth.sources.local_cli_oauth import (
    DEFAULT_CLAUDE_CREDENTIALS_PATH,
    LocalCLICredentialError,
    LocalCLICredentialSource,
)
from craik.runtime.auth.sources.oidc_exchange import OIDCTokenExchangeSecretManager
from craik.runtime.auth.sources.provider_oauth import (
    ProviderOAuthCredentialError,
    ProviderOAuthCredentialSource,
)
from craik.runtime.auth.sources.secret_ref import (
    EnvVarSecretManager,
    FileSecretManager,
    SecretManager,
    SecretRefCredentialError,
    SecretRefCredentialSource,
)
from craik.runtime.auth.sources.stigmem_ref import (
    STIGMEM_CREDENTIAL_RELATION,
    StigmemCredentialError,
    StigmemCredentialSource,
)

__all__ = [
    "DEFAULT_CLAUDE_CREDENTIALS_PATH",
    "CLIBridgeCredentialError",
    "CLIBridgeCredentialSource",
    "EnvVarApiKeySource",
    "EnvVarSecretManager",
    "AuthProfileSourceError",
    "FileSecretManager",
    "KeyringRefCredentialSource",
    "LocalCLICredentialError",
    "LocalCLICredentialSource",
    "OIDCTokenExchangeSecretManager",
    "ProviderOAuthCredentialError",
    "ProviderOAuthCredentialSource",
    "SecretManager",
    "SecretRefCredentialError",
    "SecretRefCredentialSource",
    "STIGMEM_CREDENTIAL_RELATION",
    "StigmemCredentialError",
    "StigmemCredentialSource",
    "source_for_auth_profile",
]
