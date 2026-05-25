# Slash Commands

<p className="craik-meta"><span>7 min read</span><span>For operators</span><span>Updated 2026-05-25</span></p>

<div className="craik-lead">

**What you'll do**

Use Craik's interactive command surface from inside the terminal runtime:
discover commands, read structured help, work with tabular output, search the
transcript, and confirm destructive actions before they change local state.

</div>

Slash commands are the control surface for Craik's TUI. They are available
inside `craik`, `craik --tui`, and `craik tui`; scripted and non-TTY use can
still call the same command families through the plain CLI where a stable
subcommand exists.

## Discover Commands

Type `/` to open completion, or run:

```text
/help
```

Use `/help <command>` for a full detail page:

```text
/help /provider
/help model
/help clear
```

The detail page is generated from the same registry that drives completion,
rendering, empty states, and confirmation requirements. Each page includes
usage, readiness requirements, output shape, examples, action keys, and any
confirmation warning.

Core auth, provider, model, and session commands share their structured result
builders with the plain CLI. That keeps `/auth status`, `/provider`,
`/model`, `/model list`, `/model set`, `/sessions`, and `/resume` aligned with
the command behavior operators see outside the TUI.

## Core Commands

| Command | Use |
|---|---|
| `/status` | Show readiness, active model, operator state, and policy warnings. |
| `/login` | Show operator-session login guidance for audited operator mode. |
| `/auth login [provider]` | Open credential capture without echoing secret material. |
| `/auth status` | Inspect cached credential and runtime health state. |
| `/provider` | List provider families and credential state. |
| `/model list` | List configured provider default model selectors. |
| `/model set <provider/model>` | Set the active provider/model selector. |
| `/sessions` | List persistent sessions and the active session pointer. |
| `/rename <name>` | Rename the current shell session. |
| `/resume <session-id>` | Set the active persistent session. |
| `/approvals` | Inspect pending approval requests. |
| `/approvals decide <approval-id>` | Open the approval decision modal. |
| `/receipts` | Inspect persisted capability, plugin, and gateway receipts. |
| `/receipts detail <receipt-id>` | Open a receipt detail modal. |
| `/mcp [verbose] [--json]` | Inspect configured MCP clients and discovered tools. |
| `/gateway` | Inspect gateway configs, runtime state, and schedules. |
| `/skills` | Inspect learning-loop skill packages, registries, and proposals. |
| `/memory` | Inspect memory proposals, diffs, and impact previews. |
| `/theme [dark\|light\|monochrome]` | Inspect or persist the TUI theme. |
| `/clear` | Clear the visible transcript after confirmation. |
| `/exit` | Exit the interactive shell. |

`/doctor` renders the same redacted diagnostic report as `craik doctor --json`,
including setup, gateway, channel, auth-profile, and local-store checks.

## Structured Output

Slash-command results use declarative output shapes:

| Shape | Used for | Behavior |
|---|---|---|
| `table` | Providers, sessions, approvals, receipts, MCP clients | Columnar rendering with compact overflow handling. |
| `kv` | Model, rename, resume, theme state | Two-column key/value summaries. |
| `tree` | Status, setup, gateway, skills, memory | Nested state without raw JSON walls. |
| `markdown` | Help and human-readable guidance | Formatted operator copy. |

Long table output collapses automatically and shows the expansion/search hint:

```text
... +N lines (Space=expand, Ctrl+F=find)
```

Empty command results render a plain empty state plus the registry-declared
remediation command when one exists.

## Input Intelligence

Craik watches the first token for known command names. If you type `provider`
instead of `/provider`, the TUI shows a warning toast:

```text
Did you mean `/provider`? Press Tab to convert, Enter to send to the model.
```

This is intentionally non-blocking. Press `Tab` to convert and run the slash
command, press `Enter` again to send the original text as a prompt, or press
`Esc` to dismiss the nudge.

Argument-aware help prevents common dead ends. For example, `/model set`
without a selector renders usage and examples instead of dispatching a partial
command.

## Transcript And Receipts

Press `Ctrl+F` to search the current transcript. Type the search term, press
`Enter` to move to the next match, `Backspace` to edit, and `Esc` to return to
the prompt. Search is intentionally limited to the current TUI session.

Use `/receipts detail <receipt-id>` to open a focused audit modal for a receipt.
The modal reports the receipt id, integrity state, result status, and redacted
summary. Capability receipts show receipt-chain integrity; HMAC-backed receipt
types show HMAC verification status when available.

## Confirmations

Destructive TUI actions confirm before they proceed. In v0.12.4, `/clear`
opens a modal that describes the blast radius: the visible transcript is
discarded, while persisted receipts and audit records remain stored.

Confirmation-only families such as `/policy reset`, `/migrate apply`,
`/agent delete <agent-id>`, and `/session delete <session-id>` return a
structured modal request in the TUI. Inline slash dispatch does not perform the
destructive action directly.

Confirmations record a redacted `slash.confirmation` capability receipt with
the command and decision. Declines are recorded too, so an audit trail can
distinguish "not attempted" from "explicitly declined."

`/auth logout [profile]` continues to use the credential-specific logout modal
because it needs provider/profile context and credential-store behavior.

## JSON And Automation

Use `--json` where a command supports machine-readable output, such as:

```text
/mcp --json
/mcp verbose --json
```

Inside the TUI, slash commands are optimized for operator readability. For
automation, prefer the equivalent plain CLI command when one exists so scripts
can rely on process exit codes and stable stdout.

## Related Guides

<div className="craik-next">

<a href="../terminal-ui/">
<strong>Guide</strong>
<span>Terminal UI</span>
<small>Launch, layout, history, modals, and keyboard behavior.</small>
</a>

<a href="../authentication/">
<strong>Guide</strong>
<span>Authentication</span>
<small>Provider credentials, cached profiles, and operator sessions.</small>
</a>

<a href="../privacy/">
<strong>Guide</strong>
<span>Privacy</span>
<small>Where prompts, receipts, logs, and local history are stored.</small>
</a>

</div>
