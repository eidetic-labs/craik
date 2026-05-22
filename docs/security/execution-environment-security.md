# Execution environment security

<p className="craik-meta"><span>3 min read</span><span>Security</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

How Craik records provider and sandbox decisions for persistent agents:
capability grants, redacted environment receipts, denial receipts, and
the state that may cross the execution boundary.

</div>

<div className="craik-keypoint">

**Receipts do not grant authority.**

Environment receipts are evidence. The caller must already have made the
provider, sandbox, or capability decision before recording the receipt.

</div>

## Boundary model

Persistent agents execute through the same provider-backed run path as
bounded task runs. The agent session contributes identity and continuity
links; it does not add a separate side-effect authority surface.

<div className="craik-grid">

<div><h4>Provider boundary</h4><p>The prompt loop records provider id, policy envelope id, run id, handoff id, and provider result count.</p></div>
<div><h4>Sandbox boundary</h4><p>The prompt loop records the sandbox backend id, command reference, capability, and grant outcome.</p></div>
<div><h4>Session boundary</h4><p>Receipts carry the agent session id so operator views can correlate decisions without copying secrets into session state.</p></div>

</div>

## Explicit grants

Side effects require explicit capability grants. For the deterministic
persistent-agent fixture path, Craik grants `shell.execute` only when the
operator uses the default fixture approval path. When the grant is
absent, prompt execution records a `denial` environment receipt for
`shell.execute` and keeps the run blocked.

This shape keeps tests, demos, and direct runtime callers honest: a
provider response alone is not enough to authorize a local action.

## Receipt linkage

Each persistent prompt can record two environment receipts:

| Receipt | Capability | Status |
| --- | --- | --- |
| Provider action | `model.chat` | `passed` when provider execution returned a result. |
| Sandbox action | `shell.execute` | `passed` only when the fixture action grant is present. |
| Sandbox denial | `shell.execute` | `denied` when the fixture action grant is absent. |

Receipt metadata includes the session id, task id, policy envelope id,
provider id, sandbox backend id, redacted command reference, run id, and
handoff id. The session state stores the resulting receipt ids so
inspection surfaces can move from a persistent agent to the exact
provider and sandbox records for the prompt.

## Redaction rules

Environment receipts store references, not raw payloads. Redaction
removes or masks command payloads, raw commands, environment maps,
stdin, stdout, stderr, target payloads, credentials, tokens, passwords,
API keys, and secret-like metadata keys.

Command targets use a redacted command reference such as
`sandbox_action:fixture-action`. Provider and sandbox identifiers remain
as stable routing references; credential values never appear in receipt
metadata.

## Operator checks

Use these checks when reviewing a persistent-agent run:

1. Confirm the agent session `receipt_ids` include the environment
   receipt ids for the prompt.
2. Confirm provider receipts reference the expected provider and policy
   envelope.
3. Confirm sandbox receipts show `passed` only when the capability grant
   was present.
4. Treat `denial` receipts as expected protection, not as partial
   execution.

## What's next

<div className="craik-next">

<a href="../persistent-agent-security/">
<strong>Security</strong>
<span>Persistent agent security</span>
<small>Session state, recovery, redaction, and operator boundaries.</small>
</a>

<a href="../../reference/environment-receipts/">
<strong>Reference</strong>
<span>Environment receipts</span>
<small>The receipt fields recorded for provider and sandbox decisions.</small>
</a>

<a href="../../reference/sandbox-backends/">
<strong>Reference</strong>
<span>Sandbox backends</span>
<small>The backend contract receipts link to.</small>
</a>

</div>
