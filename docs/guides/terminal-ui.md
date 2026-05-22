# Terminal UI

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Launch Craik's keyboard-first terminal UI, inspect setup status, route
slash commands, and keep model, session, approval, gateway, and skill
proposal context visible while working from a terminal.

</div>

<div className="craik-keypoint">

**Starts before setup.**

The TUI is an operator shell, not an auth gate. It can open before a
provider, model, or operator session is configured, then uses readiness
panels to show the next action instead of failing at launch.

</div>

## Launch

Use either entrypoint:

```sh
craik --tui
craik tui
```

The first render shows provider/auth status, the multiline composer,
model and session pickers, approval status, runs, handoffs, receipts,
gateway state, and skill proposal counts. The frame is intentionally
text-native so it works in local terminals, CI smoke tests, and remote
shells without a graphics stack.

## Commands

The TUI uses the same slash-command registry as the agent shell:

```text
/help
/status
/provider login openai
/model
/sessions
/approvals
/gateway
/skills
```

Use `/compose` to enter multiline input. Finish the message with a
single `.` line. Use `/redraw` to refresh the panels and `/exit` to
leave the TUI.

## What the Panels Show

<div className="craik-grid">

<div><h4>Provider/Auth Status</h4><p>Readiness state, home path, active profile, active model, missing setup, warnings, and next action.</p></div>
<div><h4>Composer</h4><p>Slash-command and multiline-input hints.</p></div>
<div><h4>Model Picker</h4><p>The active model plus commands for model list and selection.</p></div>
<div><h4>Session Picker</h4><p>Persistent session and run counts with resume guidance.</p></div>
<div><h4>Approvals</h4><p>The approval queue surface used by later approval lifecycle flows.</p></div>
<div><h4>Runs / Handoffs / Receipts</h4><p>Read-only artifact counts and redaction posture.</p></div>
<div><h4>Gateway</h4><p>Configured gateway runtime states and gateway status command hints.</p></div>
<div><h4>Skill Proposals</h4><p>Learning-loop proposal counts and governed promotion commands.</p></div>

</div>

## Security and Redaction

The TUI renders from existing readiness and local-store surfaces. It
does not bypass operator auth checks for commands that already require
an active operator session, and it keeps redaction on for dynamic text.
Panels show status, IDs, counts, and summaries rather than raw secrets.

The approval modal fixture follows the same rule: it shows capability,
target, risk, policy, and available actions while redacting secret-like
target text before it reaches the terminal.

## Accessibility

The first TUI implementation is keyboard-first and text-native. It
avoids mouse-only controls, preserves readable labels for every panel,
and keeps output deterministic for screen readers, terminal capture,
and snapshot tests. The `/help` command remains the canonical command
index for users who prefer linear navigation.

## What's next

<div className="craik-next">

<a href="../agent-shell/">
<strong>Guide</strong>
<span>Agent shell</span>
<small>The command shell that shares the TUI slash-command registry.</small>
</a>

<a href="../../reference/slash-commands/">
<strong>Reference</strong>
<span>Slash commands</span>
<small>The shared command registry used by shell, TUI, dashboard, and tests.</small>
</a>

<a href="../../reference/operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The read-only runtime views the TUI builds on.</small>
</a>

</div>
