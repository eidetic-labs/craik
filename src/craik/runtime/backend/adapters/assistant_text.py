"""Formatting-preserving assistant-text cleaning for emitted events.

The live model output interleaves prose the operator WANTS with a
``## Craik contract output`` section carrying ```json contract blocks the
operator must NEVER see. The contract JSON may carry an empty ``"schema": ""``,
so a marker-substring scrub alone misses the section. :func:`clean_assistant_text`
strips the whole section via a line-based scanner ported from the Rust TUI's
``strip_craik_contract_output_sections`` (deleted in Phase 6 on a wrong
assumption), then scrubs the bare markers, then normalizes whitespace WITHOUT
flattening markdown -- newlines/lists/fences in the kept prose survive.

Lives in its own module (not on ``base``) so the adapter foundation stays within
the file-size budget.
"""

from __future__ import annotations

# Quoted contract keys that mark a line as part of a contract JSON body.
_CONTRACT_JSON_KEYS = (
    "schema",
    "task_id",
    "status",
    "summary",
    "evidence",
    "receipt_ids",
    "commands_run",
    "capabilities_used",
    "policy_compliance",
)
# Lone horizontal-rule separators a contract section may be preceded by.
_CONTRACT_SEPARATORS = ("---", "----", "-----", "***", "___", "—", "–")


# Envelope schema ids that must never leak into emitted events even when they
# appear OUTSIDE a detected contract section (e.g. a heading-less fenced block).
# Scrubbed as bare tokens; surrounding prose is preserved.
_CONTRACT_ENVELOPE_MARKERS = ("craik.runner_step_result", "craik.handoff")


def _contract_heading_kind(lower: str) -> str | None:
    """Classify a lowercased, trimmed line as a contract heading.

    Returns ``"group"`` for a ``## Craik contract output``-style heading (whose
    body is a GROUP of fenced blocks), ``"single"`` for an inline
    ``**craik.handoff**`` / ``craik.runner_step_result`` marker heading (a single
    fenced block), or ``None`` when the line is not a contract heading.
    """
    # Only a HEADING/label line can open a contract section -- never bare prose.
    # A markdown heading ("## ...") or a bold-only label line ("**...**").
    # Otherwise sentences that merely MENTION "contract output" (or start with
    # "craik.") would be silently eaten -- a false strip is worse than the wall.
    heading_like = lower.startswith("#") or (
        lower.startswith("**") and lower.endswith("**")
    )
    if heading_like and (
        "craik contract output" in lower
        or "contract-shaped output" in lower
        or "contract output" in lower
        or "output contract" in lower
    ):
        return "group"
    # A single-marker heading: a bold-wrapped/heading "craik.*" label, or a bare
    # "craik.<token>" line with no surrounding prose (no spaces).
    if (heading_like and "craik." in lower) or (
        lower.startswith("craik.") and " " not in lower
    ):
        return "single"
    return None


def _looks_like_contract_json_line(line: str) -> bool:
    """Whether a trimmed line looks like part of a contract JSON body."""
    if line.startswith(("{", "}", "[", "]")):
        return True
    if line.endswith((",", ":")):
        return True
    lower = line.lower()
    return any(f'"{key}"' in lower for key in _CONTRACT_JSON_KEYS)


def _remove_trailing_contract_separator(output: list[str]) -> None:
    """Pop a trailing ``---``-style rule (and surrounding blanks) before a section.

    A contract section is often preceded by a horizontal rule; once we detect the
    heading we retroactively drop that rule so the kept prose does not end on a
    dangling separator. Mirrors the Rust ``remove_trailing_contract_separator``.
    """
    while output and not output[-1].strip():
        output.pop()
    if output and output[-1].strip() in _CONTRACT_SEPARATORS:
        output.pop()
    while output and not output[-1].strip():
        output.pop()


def _strip_contract_output_sections(text: str) -> str:
    """Strip ``## Craik contract output`` headings and their fenced JSON blocks.

    Line-based port of the Rust ``strip_craik_contract_output_sections``.
    Operates on RAW text WITH newlines intact (it relies on line structure), so
    callers must run it BEFORE any whitespace collapse.
    """
    output: list[str] = []
    skipping_contract = False
    skipping_fence = False
    contract_had_fence = False
    skipping_contract_group = False

    for line in text.splitlines():
        trimmed = line.strip()
        lower = trimmed.lower()

        kind = _contract_heading_kind(lower)
        if kind is not None and not skipping_contract:
            _remove_trailing_contract_separator(output)
            skipping_contract = True
            skipping_fence = False
            contract_had_fence = False
            skipping_contract_group = kind == "group"
            continue

        if skipping_contract:
            if trimmed.startswith("```"):
                if skipping_fence:
                    # Closing fence: a group keeps skipping (more blocks may
                    # follow); a single block ends here.
                    skipping_contract = skipping_contract_group
                    skipping_fence = False
                    contract_had_fence = False
                else:
                    skipping_fence = True
                    contract_had_fence = True
                continue
            if (
                skipping_fence
                or not trimmed
                or _looks_like_contract_json_line(trimmed)
                or (contract_had_fence and _contract_heading_kind(lower) is not None)
            ):
                continue
            # A non-contract, non-blank line ends the section.
            skipping_contract = False
            contract_had_fence = False
            skipping_contract_group = False
            # Drop a lone horizontal rule that immediately followed the section
            # (it was the block's trailing separator, not prose).
            if trimmed in _CONTRACT_SEPARATORS:
                continue

        output.append(line)

    return "\n".join(output)


def _normalize_preserving_structure(text: str) -> str:
    """Trim leading/trailing whitespace and collapse 3+ blank lines to one.

    PRESERVES newlines/markdown -- unlike ``" ".join(text.split())`` it never
    flattens the text to a single paragraph.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            collapsed.append(line)
        else:
            blank_run += 1
            # Keep at most ONE blank line in a run (3+ -> 1).
            if blank_run <= 1:
                collapsed.append(line)
    return "\n".join(collapsed).strip()


def clean_assistant_text(text: str) -> str:
    """Clean assistant text for operator display + persisted gateway history.

    The fix for the live "wall of text": (1) strip whole ``## Craik contract
    output`` sections (heading + fenced JSON blocks) via the line-based scanner,
    (2) scrub any residual bare envelope-schema-id tokens that appear OUTSIDE a
    detected section (a leakage guard), (3) normalize whitespace WITHOUT
    flattening markdown. The result keeps the prose + Summary the operator wants
    with newlines/lists intact, and drops the contract sections entirely.

    The section scanner (step 1) is heading-gated, so it can NEVER eat a whole
    prose line that merely mentions "contract output" or starts with "craik."
    (the prior over-strip hazard). Step 2 only removes the bare id token, never
    the surrounding sentence.

    MUST run on RAW text with newlines intact (before any whitespace collapse).
    """
    stripped = _strip_contract_output_sections(text)
    for marker in _CONTRACT_ENVELOPE_MARKERS:
        stripped = stripped.replace(marker, "")
    return _normalize_preserving_structure(stripped)


__all__ = ["clean_assistant_text"]
