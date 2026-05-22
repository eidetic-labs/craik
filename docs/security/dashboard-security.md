# Dashboard Security

<p className="craik-meta"><span>4 min read</span><span>For operators &amp; maintainers</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The security posture for Craik's local dashboard: authentication,
local bind defaults, unsafe-bind acknowledgement, redaction, and action
boundaries.

</div>

<div className="craik-keypoint">

**The dashboard is not public infrastructure.**

It is a local operator surface. Keep it bound to localhost unless a
separate network boundary and TLS termination layer are already in
place.

</div>

## Authentication

Every dashboard route requires one of two authentication postures:

<div className="craik-grid">

<div><h4>Dashboard bearer token</h4><p>Pass a token with <code>--auth-token</code> or <code>CRAIK_DASHBOARD_TOKEN</code>, then send it in <code>Authorization: Bearer ...</code> or <code>X-Craik-Dashboard-Token</code>.</p></div>
<div><h4>Active operator session</h4><p>If no dashboard token is configured, requests must include <code>X-Craik-Operator-Session</code> matching the active local session token.</p></div>

</div>

Dry-run launch metadata reports the active auth posture but does not
print the bearer token value. Operator-session mode includes a warning
that callers must send the session-binding header; the presence of an
operator-session file alone is not sufficient.

## Bind Safety

`craik dashboard` binds to `127.0.0.1` by default. Binding to
`0.0.0.0`, a LAN address, or another non-local host is rejected unless
the operator passes `--allow-unsafe-dashboard-bind`.

That flag is an acknowledgement, not a security control. Treat a
non-local dashboard as sensitive and place it behind network controls
and TLS termination.

## Redaction

Dashboard JSON and HTML are rendered through the shared redaction and
runtime text sanitization utilities. Pages expose readiness state,
counts, IDs, paths, provider status, and action output; they do not
display raw provider secrets, refresh tokens, or credential-bearing
values.

## Actions

The `/api/actions` route dispatches through the shared slash-command
registry. Browser POSTs with an `Origin` header must match the local
dashboard origin, and read-only command results are returned directly.
Mutating slash-command families are blocked from this route. Mutating
dashboard actions must route through their owning runtime handlers and
must keep receipt emission, operator identity, and policy checks in
those handlers rather than bypassing them in the web surface.

## What's next

<div className="craik-next">

<a href="../../guides/dashboard/">
<strong>Guide</strong>
<span>Local dashboard</span>
<small>Launch and operate the authenticated local dashboard.</small>
</a>

<a href="../secrets/">
<strong>Security</strong>
<span>Secrets</span>
<small>The shared redaction and secret-handling model used by dashboard rendering.</small>
</a>

<a href="../../reference/slash-commands/">
<strong>Reference</strong>
<span>Slash commands</span>
<small>The shared action registry boundary.</small>
</a>

</div>
