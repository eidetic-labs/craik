"""Pin the per-vendor permission/approval-mode passthrough against regression.

``/mode`` is one operator command but each vendor CLI has its OWN mode
vocabulary, its OWN flag, and its OWN env var. A bug previously shipped where a
fake mode (``auto``) was silently swallowed and the real high-risk modes
(``bypassPermissions`` / ``dontAsk`` / ``yolo`` / ``danger-full-access``) were
filtered out, so NO mode the operator picked actually reached the vendor CLI.
Phase 7.2 fixed it with per-vendor validators.

This guard makes that regression class un-mergeable. It drives the REAL
validators (no subprocess, no AST parsing) and asserts, per vendor:

1. The vendor's choices constant in ``mode_args.py`` exactly equals the verified
   CLI vocabulary written down below (the one pin where the verified values
   live). Dropping ``bypassPermissions`` / ``dontAsk`` / ``yolo`` /
   ``danger-full-access`` or re-adding a fake mode FAILS here.
2. Every real mode, fed to the vendor's validator, returns a truthy passthrough
   value (the mode is NOT dropped).
3. Bogus tokens (``auto`` — the exact original bug — and ``nonsense``) fed to
   each validator return falsy (NOT silently coerced to a permissive default).

The verified CLI vocabularies (source of truth, confirmed against the installed
CLIs):

* claude  ``--permission-mode``  {default, acceptEdits, plan, dontAsk, bypassPermissions}
* gemini  ``--approval-mode``    {default, auto_edit, yolo, plan}
* codex   ``--sandbox``          {read-only, workspace-write, danger-full-access}
"""

from __future__ import annotations

import sys

from craik.runtime.backend.claude_code_settings import (
    CLAUDE_PERMISSION_MODE_ENV,
    CODEX_SANDBOX_MODE_ENV,
    GEMINI_APPROVAL_MODE_ENV,
    _claude_permission_mode,
    _codex_sandbox_mode,
    _gemini_approval_mode,
)
from craik.runtime.shell.contract_runtime.mode_args import (
    CLAUDE_PERMISSION_MODE_CHOICES,
    CODEX_SANDBOX_MODE_CHOICES,
    GEMINI_APPROVAL_MODE_CHOICES,
)

# The verified per-vendor CLI vocabularies. This literal is the pin: the guard
# compares the live choices constants against it as sets, so any future edit
# that drops a real high-risk mode or re-adds a fake one fails the guard.
CLAUDE_VERIFIED = frozenset({"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"})
GEMINI_VERIFIED = frozenset({"default", "auto_edit", "yolo", "plan"})
CODEX_VERIFIED = frozenset({"read-only", "workspace-write", "danger-full-access"})

# Tokens that must NEVER pass any validator. ``auto`` is the exact original bug
# (a fake Claude mode); ``nonsense`` is a generic foreign token.
BOGUS_TOKENS = ("auto", "nonsense")


def _normalized_choices(choices: tuple[str, ...]) -> frozenset[str]:
    """Map operator-facing choices to their stored/CLI vocabulary.

    Claude exposes ``ask`` as the display alias of the stored ``default`` token;
    the validator vocabulary uses ``default``. Normalize so the set comparison
    is against the real CLI vocabulary, not the display labels.
    """
    return frozenset("default" if choice == "ask" else choice for choice in choices)


def check_vendor() -> list[str]:
    """Return per-vendor failures pinning the mode passthrough. Empty == OK."""
    failures: list[str] = []

    vendors = (
        (
            "claude",
            CLAUDE_PERMISSION_MODE_CHOICES,
            CLAUDE_VERIFIED,
            CLAUDE_PERMISSION_MODE_ENV,
            _claude_permission_mode,
        ),
        (
            "gemini",
            GEMINI_APPROVAL_MODE_CHOICES,
            GEMINI_VERIFIED,
            GEMINI_APPROVAL_MODE_ENV,
            _gemini_approval_mode,
        ),
        (
            "codex",
            CODEX_SANDBOX_MODE_CHOICES,
            CODEX_VERIFIED,
            CODEX_SANDBOX_MODE_ENV,
            _codex_sandbox_mode,
        ),
    )

    for name, choices, verified, env_var, validator in vendors:
        # (1) choices constant must exactly equal the verified CLI vocabulary.
        live = _normalized_choices(choices)
        if live != verified:
            missing = sorted(verified - live)
            extra = sorted(live - verified)
            failures.append(
                f"{name}: choices constant drifted from verified CLI vocab"
                f" (missing={missing}, unexpected={extra})"
            )

        # (2) every real mode must pass the validator (not silently dropped).
        for mode in sorted(verified):
            passed = validator({env_var: mode})
            if not passed:
                failures.append(
                    f"{name}: real mode {mode!r} dropped by validator"
                    f" (returned {passed!r}) — operator's chosen mode would not reach the CLI"
                )

        # (3) bogus tokens must be rejected (not coerced to a permissive default).
        for bogus in BOGUS_TOKENS:
            rejected = validator({env_var: bogus})
            if rejected:
                failures.append(
                    f"{name}: bogus token {bogus!r} accepted by validator"
                    f" (returned {rejected!r}) — fake mode silently passed through"
                )

    return failures


def main() -> int:
    failures = check_vendor()
    if failures:
        print("Vendor mode-passthrough guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Vendor mode-passthrough guard passed: claude/gemini/codex vocab pinned"
        " and every real mode reaches its CLI."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
