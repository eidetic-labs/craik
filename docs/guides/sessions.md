# Sessions

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Name an interactive Craik session, rename it from the TUI, carry that name
into launched agents, and inspect persistent agent session labels.

</div>

## Session Names

Craik uses session names as operator-visible labels. They are separate from
stable session ids and do not grant access, change policy, or rewrite receipt
history.

Valid names may contain letters, numbers, spaces, `_`, and `-`. Names must be
1 to 64 characters, may not start or end with whitespace, and may not contain
control characters.

Start the TUI with a shell session name:

```sh
craik --name "Desk review"
craik tui --name "Desk review"
```

Rename the current shell session without restarting:

```text
/rename Desk review
```

The TUI status bar and `/sessions` output show the current shell session name.
The name is persisted under Craik's local config directory and is also kept in
the in-process TUI environment for commands launched from the same shell.

The shell name is intentionally lightweight. It helps operators correlate a
terminal tab, local shell receipts, and persistent sessions started from that
tab, but it is not an authorization factor and is not treated as identity.

## Persistent Agents

Persistent agent sessions keep a `display_name` alongside their stable
session id. Launch with an explicit label:

```sh
craik agent launch --provider openai --name "Planning desk"
```

If a shell session already has a name, `craik agent launch` inherits it through
`CRAIK_SESSION_NAME` unless `--name` is supplied. This makes agents started
from a named TUI easy to connect back to the operator workflow that spawned
them.

Rename an existing persistent agent session:

```sh
craik agent rename <session-id> "Planning desk"
```

Renaming the shell session later does not retroactively rename already-spawned
agents. Use `craik agent rename` when a persistent agent should receive a new
label.

## Review Flow

When reviewing a named session, check these surfaces together:

1. `/sessions` for the active shell session and persistent agent labels.
2. `craik agent list` for stable session ids and current lifecycle state.
3. Shell invocation receipts for local commands started from a named TUI.
4. Provider and sandbox receipts for prompts run through persistent agents.

## Privacy

Session names are local metadata and may appear in local status output,
session records, and operator-facing diagnostics. Do not place secrets,
customer credentials, or sensitive prompt content in a session name.

## Related Guides

<div className="craik-next">

<a href="../terminal-ui/">
<strong>Guide</strong>
<span>Terminal UI</span>
<small>Interactive launch, slash commands, history, themes, and modal flows.</small>
</a>

<a href="../persistent-agent-runtime/">
<strong>Guide</strong>
<span>Persistent agent runtime</span>
<small>Agent lifecycle state, supervision, restart, and recovery behavior.</small>
</a>

</div>
