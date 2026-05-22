# Local Dashboard

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Launch Craik's authenticated local dashboard, inspect runtime status,
and use browser pages for providers, sessions, runs, handoffs,
receipts, approvals, gateway logs, skill proposals, and model state.

</div>

<div className="craik-keypoint">

**Local first, authenticated always.**

The dashboard binds to `127.0.0.1` by default. Every route requires
either a dashboard bearer token or an active operator session; non-local
binds require an explicit unsafe-bind acknowledgement.

</div>

## Launch

Use the dashboard command from a terminal:

```sh
craik dashboard
```

For automation or tests, inspect launch metadata without starting the
server:

```sh
craik dashboard --dry-run
```

You can provide a dashboard token through `--auth-token` or
`CRAIK_DASHBOARD_TOKEN`. The dry-run output reports that token mode is
active but does not echo the token value. If no dashboard token is
configured, requests must include `X-Craik-Operator-Session` with the
active operator session token.

## Pages

<div className="craik-grid">

<div><h4>Status</h4><p>Readiness state, selected model, missing setup, and operator posture.</p></div>
<div><h4>Config · Providers · Auth</h4><p>Local dashboard posture, visible provider profiles, and auth requirement state.</p></div>
<div><h4>Sessions · Runs</h4><p>Persistent agent session and task-run counts from local state.</p></div>
<div><h4>Handoffs · Receipts</h4><p>Read-only artifact counts with redacted output boundaries.</p></div>
<div><h4>Approvals</h4><p>The dashboard queue surface for approval lifecycle work.</p></div>
<div><h4>Gateway Logs</h4><p>The configured gateway log location and runtime status entrypoint.</p></div>
<div><h4>Skill Proposals</h4><p>Learning-loop proposal counts and operator action links.</p></div>
<div><h4>Models</h4><p>The active model picker state used by the shell and TUI.</p></div>

</div>

## Actions

The dashboard exposes a shared action route for slash commands:

```http
POST /api/actions
Authorization: Bearer <dashboard-token>

{"command": "/status"}
```

Read-only actions return the same slash-command result text as the
agent shell and TUI. Browser-origin POSTs must come from the local
dashboard origin, and mutating slash-command families such as auth,
provider login, model selection, and session resume are rejected by the
dashboard action route. Those flows stay governed by their own
CLI/runtime handlers and receipt requirements.

## Binding

Use the default local-only bind whenever possible:

```sh
craik dashboard --host 127.0.0.1 --port 8787
```

Non-local binds are blocked unless explicitly acknowledged:

```sh
craik dashboard --host 0.0.0.0 --allow-unsafe-dashboard-bind --auth-token "$CRAIK_DASHBOARD_TOKEN"
```

Only use this behind local network controls or a trusted TLS
termination layer.

## What's next

<div className="craik-next">

<a href="../terminal-ui/">
<strong>Guide</strong>
<span>Terminal UI</span>
<small>The keyboard-first shell that shares the dashboard action registry.</small>
</a>

<a href="../../security/dashboard-security/">
<strong>Security</strong>
<span>Dashboard security</span>
<small>Authentication, binding, and redaction requirements for local dashboard use.</small>
</a>

<a href="../../reference/slash-commands/">
<strong>Reference</strong>
<span>Slash commands</span>
<small>The shared command registry used by shell, TUI, dashboard, and tests.</small>
</a>

</div>
