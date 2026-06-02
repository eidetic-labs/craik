"""Per-vendor permission-mode arguments for the universal ``/mode`` command.

``/mode`` is ONE command, but each vendor's CLI has its OWN permission-mode
vocabulary + its OWN env var (capture, don't force — the operator's chosen mode
must reach each vendor faithfully):

* anthropic (Claude): ``--permission-mode`` {default, acceptEdits, plan, dontAsk,
  bypassPermissions}; ``ask`` is a display alias of ``default``.
* google (Gemini): ``--approval-mode`` {default, auto_edit, yolo, plan};
  ``yolo`` is the high-risk bypass-equivalent.
* openai (Codex): ``--sandbox`` {read-only, workspace-write, danger-full-access};
  ``danger-full-access`` is the high-risk bypass-equivalent. Observe-only.

This module owns the per-vendor mode tables and resolves the ACTIVE vendor (via
``_active_provider_and_model`` + ``normalize_provider_family``) so the command,
the TUI cycle, and the slash spec all validate/store against the right vendor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from craik.runtime.backend.claude_code_settings import (
    CLAUDE_PERMISSION_MODE_ENV,
    CODEX_SANDBOX_MODE_ENV,
    GEMINI_APPROVAL_MODE_ENV,
    _active_provider_and_model,
)
from craik.runtime.providers.provider_transport import normalize_provider_family

# Public API of this module (consumed by the slash command, slash spec, TUI, and
# catalog). Declaring it also tells the unused-global analysis that the
# choice tuples are exports, not dead module-level state.
__all__ = [
    "CLAUDE_PERMISSION_MODE_CHOICES",
    "GEMINI_APPROVAL_MODE_CHOICES",
    "CODEX_SANDBOX_MODE_CHOICES",
    "ALL_PERMISSION_MODE_CHOICES",
    "VendorModeSpec",
    "stored_permission_mode",
    "display_permission_mode",
    "active_vendor_mode_spec",
]

# Claude's user-facing choices keep ``ask`` (the display alias of ``default``)
# in the list and DROP the internal ``default`` token — matching the original
# Claude-only ``/mode`` UX.
CLAUDE_PERMISSION_MODE_CHOICES = (
    "ask",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
)
GEMINI_APPROVAL_MODE_CHOICES = (
    "default",
    "auto_edit",
    "yolo",
    "plan",
)
CODEX_SANDBOX_MODE_CHOICES = (
    "read-only",
    "workspace-write",
    "danger-full-access",
)


@dataclass(frozen=True, slots=True)
class VendorModeSpec:
    """Resolved permission-mode surface for one vendor family.

    ``family`` is the normalized provider family (``anthropic`` | ``google`` |
    ``openai``). ``env_var`` is where the chosen mode is stored. ``choices`` are
    the operator-facing values (Claude exposes ``ask`` not ``default``).
    ``store`` validates a requested mode and returns the value to persist (or
    raises ``ValueError``). ``display`` maps a stored value to its display form.
    ``default_display`` is the status value when nothing is stored yet.
    """

    family: str
    label: str
    env_var: str
    choices: tuple[str, ...]
    high_risk: tuple[str, ...]
    # The ordered STORED values the TUI Shift-Tab cycle steps through (what is
    # written to ``env_var``). Distinct from ``choices`` (operator-facing labels)
    # only for Claude, where ``default`` is stored but ``ask`` is shown.
    cycle: tuple[str, ...]

    def store(self, mode: str) -> str:
        raise NotImplementedError

    def display(self, mode: str) -> str:
        return mode

    def current(self, env: Mapping[str, str]) -> str:
        return self.display(env.get(self.env_var, self._default_stored()))

    def next_stored(self, env: Mapping[str, str]) -> str:
        """Return the next stored mode in the cycle for the active vendor."""
        current = env.get(self.env_var, self._default_stored())
        try:
            index = self.cycle.index(current)
        except ValueError:
            index = 0
            return self.cycle[index]
        return self.cycle[(index + 1) % len(self.cycle)]

    def _default_stored(self) -> str:
        raise NotImplementedError


class _ClaudeModeSpec(VendorModeSpec):
    def store(self, mode: str) -> str:
        return stored_permission_mode(mode)

    def display(self, mode: str) -> str:
        return display_permission_mode(mode)

    def _default_stored(self) -> str:
        return "default"


class _PlainModeSpec(VendorModeSpec):
    """A vendor whose CLI mode tokens are also their display + stored values."""

    def store(self, mode: str) -> str:
        if mode in self.choices:
            return mode
        raise ValueError(mode)

    def _default_stored(self) -> str:
        return self.choices[0]


def stored_permission_mode(mode: str) -> str:
    if mode in {"ask", "default"}:
        return "default"
    if mode in CLAUDE_PERMISSION_MODE_CHOICES:
        return mode
    raise ValueError(mode)


def display_permission_mode(mode: str) -> str:
    return "ask" if mode == "default" else mode


_CLAUDE_MODE_SPEC = _ClaudeModeSpec(
    family="anthropic",
    label="Claude",
    env_var=CLAUDE_PERMISSION_MODE_ENV,
    choices=CLAUDE_PERMISSION_MODE_CHOICES,
    high_risk=("dontAsk", "bypassPermissions"),
    # Stored values (``default``, not the ``ask`` display alias).
    cycle=("default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"),
)
_GEMINI_MODE_SPEC = _PlainModeSpec(
    family="google",
    label="Gemini",
    env_var=GEMINI_APPROVAL_MODE_ENV,
    choices=GEMINI_APPROVAL_MODE_CHOICES,
    high_risk=("yolo",),
    cycle=GEMINI_APPROVAL_MODE_CHOICES,
)
_CODEX_MODE_SPEC = _PlainModeSpec(
    family="openai",
    label="Codex",
    env_var=CODEX_SANDBOX_MODE_ENV,
    choices=CODEX_SANDBOX_MODE_CHOICES,
    high_risk=("danger-full-access",),
    cycle=CODEX_SANDBOX_MODE_CHOICES,
)

_SPEC_BY_FAMILY: dict[str, VendorModeSpec] = {
    "anthropic": _CLAUDE_MODE_SPEC,
    "google": _GEMINI_MODE_SPEC,
    "openai": _CODEX_MODE_SPEC,
}

# The union of every vendor's modes, in vendor order. Used where a single,
# vendor-neutral choice list is needed (the slash usage/spec when the active
# vendor is not resolvable). Deduplicated, order-preserving.
ALL_PERMISSION_MODE_CHOICES: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *CLAUDE_PERMISSION_MODE_CHOICES,
            *GEMINI_APPROVAL_MODE_CHOICES,
            *CODEX_SANDBOX_MODE_CHOICES,
        ]
    )
)


def _family_for_provider(provider_id: str | None) -> str:
    """Map a provider id/name to a normalized vendor family.

    ``_active_provider_and_model`` returns ids like ``provider_anthropic`` /
    ``provider_google`` / ``provider_openai`` (and local families). Strip the
    ``provider_`` prefix and normalize so ``normalize_provider_family`` can map
    aliases (claude->anthropic, gemini->google) consistently with the rest of
    the runtime.
    """
    raw = (provider_id or "").removeprefix("provider_")
    return normalize_provider_family(raw)


def active_vendor_mode_spec(env: Mapping[str, str] | None) -> VendorModeSpec:
    """Return the ``VendorModeSpec`` for the ACTIVE provider's vendor family.

    Falls back to the Claude spec when the active family is not one of the three
    permission-mode vendors (e.g. a local OpenAI-compatible endpoint) — Claude is
    the reference surface and its ``default`` is the safe no-op.
    """
    provider_id, _model = _active_provider_and_model(None if env is None else dict(env))
    family = _family_for_provider(provider_id)
    return _SPEC_BY_FAMILY.get(family, _CLAUDE_MODE_SPEC)
