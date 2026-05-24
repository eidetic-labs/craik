# Terminal UI

<p className="craik-meta"><span>6 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Launch Craik's canonical interactive runtime, work from a chat-first
terminal surface, use slash commands without leaving the TUI, and review
auth or approval decisions in inline modal flows.

</div>

<div className="craik-keypoint">

**Starts before setup.**

The TUI is an operator shell, not an auth gate. It opens before a provider,
model, or operator session is configured, then shows readiness state and
next actions from inside the same interface.

</div>

## Launch

Use `craik` in an interactive terminal. Craik detects the TTY and launches
the Textual TUI by default:

```sh
craik
```

Add `--name` to label the shell session in the status bar and `/sessions`
output:

```sh
craik --name "Desk review"
```

The explicit TUI entrypoints still work:

```sh
craik --tui
craik tui
```

Use `--no-tui` or `CRAIK_NO_TUI=1` when you need the plain shell path for
debugging, scripts, or terminal compatibility checks:

```sh
craik --no-tui
CRAIK_NO_TUI=1 craik
```

Non-TTY use stays plain-output by design. Piped commands, CI jobs, and
scripted invocations do not open the TUI.

## Layout

<div className="craik-grid">

<div><h4>Transcript</h4><p>Scrollable prompt, response, link, and audit-trail output.</p></div>
<div><h4>Slash Popup</h4><p>Command and argument completions while typing <code>/</code>.</p></div>
<div><h4>Working Indicator</h4><p>Elapsed-time status while an agent task is in flight.</p></div>
<div><h4>Input</h4><p>Bordered prompt region with CLI-prefix detection and paste collapse.</p></div>
<div><h4>Status Bar</h4><p><code>Craik · model · state · mode · usage · quota · policy · cwd</code> at the bottom edge, omitting unavailable optional fields.</p></div>
<div><h4>Modals</h4><p>Focused auth, logout, and approval decisions without leaving the runtime.</p></div>

</div>

The bottom status bar uses the Craik brand accent for the wordmark and
subdued terminal colors for model, readiness, mode, and working directory.
Token and quota indicators shift from green to yellow, orange, and red as
available capacity tightens. Provider quota data is shown only when the
provider exposes non-sensitive rate-limit headers; unauthorized or missing
quota endpoints are hidden instead of producing noisy warnings. When the
active local policy auto-approves capabilities, the bar includes an
`auto-approve` indicator and `/status` includes the matching policy id and
operator-review warning.
`CRAIK_THEME=dark|light|monochrome` overrides auto-detection. `NO_COLOR=1`
uses the monochrome path. Use `/theme dark`, `/theme light`, or
`/theme monochrome` to persist a theme without restarting the TUI.

## Commands

The TUI uses slash commands as the primary operator control surface:

```text
/help
/status
/auth login openai
/auth status
/provider
/model list
/model set openai/gpt-4o-mini
/sessions
/rename Desk review
/resume <session-id>
/theme light
/approvals
/approvals decide <approval-id>
/gateway
/skills
/mcp
/mcp verbose
/exit
```

Commands either execute inline, print structured status into the transcript,
or open a modal. They do not route you back to shell commands while you are
inside the TUI.

`/mcp` summarizes configured MCP clients from Craik local state. Use
`/mcp verbose` to inspect policy, receipt, redaction, and advertised tool
metadata, or add `--json` when another tool needs structured output.

Prefix a line with `!` to run a local command without model involvement:

```text
! npm test
```

Shell mode executes through Craik's local-process backend with `shell=False`.
Each invocation writes a redacted `shell_invocation` receipt, HMAC signs it,
and stores redacted stdout/stderr side logs under
`~/.craik/state/shell-output/`.

Use `/rename <name>` to rename the current shell session. Valid names are 1 to
64 characters and may contain letters, numbers, spaces, `_`, and `-`. The name
is local operator metadata, so avoid putting secrets or prompt content in it.

If you accidentally type a shell command shape such as
`craik auth login openai` into the TUI prompt, Craik leaves your input in
place and shows a warning with the matching slash-command path. Press
`Ctrl-D` to exit if you intended to run a command from your operator shell.

## Walkthrough

Use this path to verify the v0.12.3 interactive surface from a clean local
home without choosing a provider first:

```text
craik --name "Desk review"
/status
/theme monochrome
/rename Desk review
/mcp
! python -c "print('walkthrough')"
/sessions
/help
```

Expected behavior:

<div className="craik-grid">

<div><h4>Launch</h4><p>The TUI opens before auth and keeps setup guidance in <code>/status</code>.</p></div>
<div><h4>Name</h4><p>The status bar and <code>/sessions</code> show <code>Desk review</code>.</p></div>
<div><h4>Theme</h4><p><code>/theme monochrome</code> persists the monochrome terminal palette.</p></div>
<div><h4>MCP</h4><p><code>/mcp</code> reports configured clients or the empty-state import hint.</p></div>
<div><h4>Shell</h4><p>The <code>!</code> command returns output inline and records a signed shell receipt.</p></div>
<div><h4>Recovery</h4><p>Misspelled CLI commands outside the TUI show close command suggestions.</p></div>

</div>

## Completion

Slash completion starts when you type `/`. Completion is context-aware:

<div className="craik-grid">

<div><h4><code>/auth login </code></h4><p>Lists configured provider families.</p></div>
<div><h4><code>/model set </code></h4><p>Lists aliases and provider default model selectors.</p></div>
<div><h4><code>/resume </code></h4><p>Lists persistent sessions sorted by recent activity.</p></div>
<div><h4><code>/approvals decide </code></h4><p>Lists open approval ids.</p></div>

</div>

Typing `@` opens file mention completion for paths under the current working
directory. Selected paths are inserted as `@path` tokens and resolved by the
runtime when the prompt is submitted.

## Input Ergonomics

Press `Ctrl+R` to open reverse history search above the input region. Typing
filters local shell history newest-first, `Up` and `Down` move through matches,
`Tab` inserts the selected match, and `Enter` submits it immediately. `Esc`
dismisses without modifying the input. `Ctrl+S` cycles the search label through
session, project, and all-history scopes.

Press `Ctrl+G` to open the current input buffer in an external editor. Craik
uses `$EDITOR`, then `$VISUAL`, then `vi` when available. The temporary file is
created under `~/.craik/state/external-editor/` with owner-only POSIX
permissions and is removed after the editor exits. If the editor fails, the
original input stays unchanged.

Multi-line input works through four equivalent paths:

| Method | Use |
|---|---|
| Shift+Enter | Native terminal newline where supported. |
| `\` + Enter | Universal continuation marker; Craik removes the trailing backslash. |
| Ctrl+J | Universal terminal newline binding. |
| Option/Alt+Enter | Meta newline where the terminal sends Option/Alt as Meta. |

## History

The TUI persists prompt and slash-command history locally:

| Mode | History file |
|---|---|
| Single-operator local | `~/.craik/state/shell-history.jsonl` |
| Audited operator mode | `~/.craik/state/shell-history-<subject-hash>.jsonl` |
| Audited mode without a session yet | `~/.craik/state/shell-history-anonymous.jsonl` |

History files use owner-only permissions on POSIX systems. The default cap is
10,000 entries. Set `CRAIK_HISTORY_MAX_ENTRIES=0` to disable persistence.

## Modal Flows

`/auth login [provider]` opens a credential capture modal with a provider
picker and password-masked credential input. The modal verifies the credential
before writing the cached profile and never writes credential material to the
transcript.

`/auth logout [profile]` opens a confirmation modal before removing a cached
profile or keyring reference.

`/approvals decide <approval-id>` opens an approval decision modal with the
capability, target, risk, policy, and retry path. Approve or deny with a
reason; Craik records a redacted decision receipt.

## Transcript Signals

Craik uses transcript widgets to keep runtime state visible:

- Action markers show tool actions, waiting states, approvals, and review
  events tied back to receipt ids.
- Section dividers separate turns.
- Long output collapses after three lines and can expand inline.
- URLs render as terminal links where supported.
- Pasted content with three or more lines collapses to `[N lines of text]`
  in the input while preserving the full submitted content.

## Security and Redaction

The TUI renders from the same readiness, auth, policy, receipt, and local-store
surfaces used by the CLI and dashboard. It does not bypass operator gates for
mutating actions. Read-only diagnostics are available before auth so operators
can understand setup state and fix configuration without leaving the runtime.

Credential input is masked and redacted. Approval modals show bounded context:
capability, target, risk, policy, retry path, and decision receipt ids.

## Accessibility

The TUI is keyboard-first and text-native. It avoids mouse-only controls,
keeps labels visible, and leaves `/help` as the linear command index. The
footer displays active key bindings. Fixed bindings keep behavior predictable
across macOS Terminal, iTerm, Linux terminals, and Windows Terminal.

## Related Guides

<div className="craik-next">

<a href="../agent-shell/">
<strong>Guide</strong>
<span>Agent shell</span>
<small>The plain shell path used for non-TTY and compatibility fallback.</small>
</a>

<a href="../authentication/">
<strong>Guide</strong>
<span>Authentication</span>
<small>Provider credential capture, cached profiles, and operator sessions.</small>
</a>

<a href="../privacy/">
<strong>Guide</strong>
<span>Privacy</span>
<small>Where prompts, receipts, logs, and history go.</small>
</a>

<a href="../sessions/">
<strong>Guide</strong>
<span>Sessions</span>
<small>Name shell sessions and persistent agent sessions.</small>
</a>

</div>
