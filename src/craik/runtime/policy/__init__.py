"""Policy runtime helpers."""

from __future__ import annotations

from craik.runtime.policy.envelope import is_auto_approve_shape
from craik.runtime.policy.policy import (
    AUTOMATION_ALLOWED_CAPABILITIES,
    AUTOMATION_APPROVAL_REQUIRED,
    AUTOMATION_DENIED_CAPABILITIES,
    STRICT_ALLOWED_CAPABILITIES,
    STRICT_APPROVAL_REQUIRED,
    STRICT_DENIED_CAPABILITIES,
    TRUSTED_LOCAL_ALLOWED_CAPABILITIES,
    TRUSTED_LOCAL_APPROVAL_REQUIRED,
    TRUSTED_LOCAL_DENIED_CAPABILITIES,
    CapabilityDeniedError,
    FailOpenNotAllowedError,
    GrantDecision,
    PolicyError,
    check_file_write_grant,
    check_github_grant,
    check_memory_grant,
    check_shell_grant,
    denial_receipt,
    fail_open_receipt,
    generate_policy_envelope,
    is_immutable_path,
)

__all__ = [
    "AUTOMATION_ALLOWED_CAPABILITIES",
    "AUTOMATION_APPROVAL_REQUIRED",
    "AUTOMATION_DENIED_CAPABILITIES",
    "STRICT_ALLOWED_CAPABILITIES",
    "STRICT_APPROVAL_REQUIRED",
    "STRICT_DENIED_CAPABILITIES",
    "TRUSTED_LOCAL_ALLOWED_CAPABILITIES",
    "TRUSTED_LOCAL_APPROVAL_REQUIRED",
    "TRUSTED_LOCAL_DENIED_CAPABILITIES",
    "CapabilityDeniedError",
    "FailOpenNotAllowedError",
    "GrantDecision",
    "PolicyError",
    "check_file_write_grant",
    "check_github_grant",
    "check_memory_grant",
    "check_shell_grant",
    "denial_receipt",
    "fail_open_receipt",
    "generate_policy_envelope",
    "is_auto_approve_shape",
    "is_immutable_path",
]
