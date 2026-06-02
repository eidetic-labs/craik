"""Tests for the formatting-preserving assistant-text cleaner.

The cleaner replaces the old whitespace-collapsing ``strip_contract_envelopes``
behavior on the assistant-text paths. It must:

* strip the ``## Craik contract output`` heading and its ```json blocks (the
  contract sections the operator must never see) even when the contract JSON
  carries an EMPTY ``"schema": ""`` (so no marker substring is present),
* still strip the ``craik.runner_step_result`` / ``craik.handoff`` markers when
  they ARE present,
* PRESERVE markdown structure -- newlines, lists, fences in the kept prose --
  rather than flattening everything to a single paragraph.
"""

from __future__ import annotations

from craik.runtime.backend.adapters.assistant_text import clean_assistant_text

# The real production output shape (live anthropic-cli dogfooding evidence):
# prose the operator WANTS, then a "## What I can see" list, then the hidden
# ``## Craik contract output`` heading with two ```json blocks whose contract
# JSON has an EMPTY ``"schema": ""``, a ``---`` separator, then the closing
# Summary prose the operator WANTS.
_REAL_OUTPUT = """Yes — I can see the Craik repo. Here is what I found.

## What I can see
- **Repo root:** `/Users/bjones/Desktop/craik`
- **Branch:** `main`

## Craik contract output
```json
{
  "schema": "",
  "task_id": "task-123",
  "status": "succeeded",
  "result": {"files_changed": []},
  "commands_run": ["ls", "git status"]
}
```
```json
{
  "schema": "",
  "from": "claude-code",
  "task_id": "task-123",
  "summary": "Inspected the repo.",
  "next_steps": []
}
```
---
**Summary:** Files changed: none. The repo is clean and on main."""


def test_cleaner_strips_contract_sections_and_preserves_formatting() -> None:
    cleaned = clean_assistant_text(_REAL_OUTPUT)

    # The contract sections are GONE: no heading, no fences, no contract JSON.
    assert "Craik contract output" not in cleaned
    assert "```" not in cleaned
    assert '"task_id"' not in cleaned
    assert '"schema"' not in cleaned
    assert "commands_run" not in cleaned

    # The prose the operator WANTS survives -- both opening and closing.
    assert "Yes — I can see the Craik repo." in cleaned
    assert "**Summary:** Files changed: none." in cleaned
    # The intermediate list the operator wants survives too.
    assert "## What I can see" in cleaned
    assert "**Repo root:**" in cleaned

    # Formatting is PRESERVED -- the result is multi-line, not flattened.
    assert "\n" in cleaned
    assert cleaned.count("\n") >= 3


def test_cleaner_strips_single_marker_style_heading() -> None:
    # A ``**craik.handoff**``-style Single heading followed by its JSON block.
    text = """Done with the work.

**craik.handoff**
```json
{"schema": "craik.handoff", "task_id": "t1", "summary": "ok"}
```

All good."""
    cleaned = clean_assistant_text(text)

    assert "Done with the work." in cleaned
    assert "All good." in cleaned
    assert "craik.handoff" not in cleaned
    assert "```" not in cleaned
    assert '"task_id"' not in cleaned


def test_cleaner_passes_through_text_with_no_contract_section() -> None:
    text = "Here is a normal answer.\n\n- one\n- two\n\nThanks!"
    cleaned = clean_assistant_text(text)

    assert "Here is a normal answer." in cleaned
    assert "- one" in cleaned
    assert "- two" in cleaned
    assert "Thanks!" in cleaned
    # Newlines preserved (not flattened).
    assert "\n" in cleaned


def test_cleaner_strips_section_even_when_marker_strings_present() -> None:
    # When the contract JSON DOES carry the marker substrings, they are stripped
    # along with the whole section.
    text = """Prose first.

## Craik contract output
```json
{"schema": "craik.runner_step_result", "task_id": "t", "status": "succeeded"}
```

Closing prose."""
    cleaned = clean_assistant_text(text)

    assert "Prose first." in cleaned
    assert "Closing prose." in cleaned
    assert "craik.runner_step_result" not in cleaned
    assert "Craik contract output" not in cleaned
    assert "```" not in cleaned


def test_cleaner_collapses_excess_blank_lines_but_keeps_single() -> None:
    text = "First.\n\n\n\n\nSecond."
    cleaned = clean_assistant_text(text)
    # 3+ blank lines collapse to a single blank line (one separating newline pair).
    assert cleaned == "First.\n\nSecond."


def test_cleaner_trims_leading_and_trailing_whitespace() -> None:
    text = "\n\n   Hello there.   \n\n"
    cleaned = clean_assistant_text(text)
    assert cleaned == "Hello there."


def test_cleaner_does_not_eat_prose_that_mentions_contract_output() -> None:
    # A FALSE strip of real model output is worse than the wall: prose that
    # merely mentions "contract output" (not a heading) must survive intact.
    text = (
        "Let me explain the contract output format we use.\n"
        "It is a JSON envelope the runner emits.\n"
        "You asked how the output contract works -- here is the answer."
    )
    out = clean_assistant_text(text)
    assert "Let me explain the contract output format we use." in out
    assert "You asked how the output contract works" in out


def test_cleaner_keeps_prose_around_a_scrubbed_marker_token() -> None:
    # The bare envelope-id token is scrubbed (leakage guard), but the
    # surrounding SENTENCE survives -- the heading-gated section scanner never
    # eats a whole prose line that merely starts with "craik.".
    text = "craik.runner_step_result is the schema name we emit for receipts."
    out = clean_assistant_text(text)
    assert "is the schema name we emit for receipts." in out


def test_cleaner_still_strips_real_markdown_heading_section() -> None:
    # The genuine heading form ("## Craik contract output") must still strip.
    text = (
        "Here is the answer.\n\n"
        "## Craik contract output\n"
        "```json\n"
        '{ "schema": "", "task_id": "t1", "status": "ok" }\n'
        "```\n"
    )
    out = clean_assistant_text(text)
    assert "Here is the answer." in out
    assert "Craik contract output" not in out
    assert '"task_id"' not in out


def test_cleaner_drops_trailing_separator_after_stripped_section() -> None:
    text = (
        "Prose before.\n\n"
        "## Craik contract output\n"
        "```json\n"
        '{ "task_id": "t1" }\n'
        "```\n"
        "---\n"
        "**Summary:** done."
    )
    out = clean_assistant_text(text)
    assert "**Summary:** done." in out
    assert "---" not in out
