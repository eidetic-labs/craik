# Environment receipts

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

How provider, MCP, sandbox, local-process, remote-shell, browser, and
container decisions persist as `craik.capability_receipt` records —
context, actions, redaction, and the boundary on what the builder
does (and doesn't) do.

</div>

<div className="craik-keypoint">

**The builder records; it doesn't execute.**

The builder in `craik.runtime.environment_receipts` does not execute
actions or grant authority. It produces auditable, redacted receipt
records for callers that have already made provider or sandbox routing
decisions.

</div>

## Receipt context

`EnvironmentReceiptContext` links receipts to:

<div className="craik-grid">

<div><h4>Task id</h4></div>
<div><h4>Agent session id</h4></div>
<div><h4>Policy envelope id</h4></div>
<div><h4>Provider id</h4></div>
<div><h4>Sandbox backend id</h4></div>
<div><h4>Route id</h4></div>
<div><h4>Target id</h4></div>
<div><h4>Command reference</h4></div>
<div><h4>Prior receipt ids</h4></div>

</div>

`agent_session_id` is optional for one-shot runs and populated by the
persistent-agent prompt loop. Operator views use it to correlate
provider actions, sandbox decisions, denials, handoffs, and recovery
state without duplicating raw prompt, command, or credential material in
the session record.

## Actions

<div className="craik-fields">

<div>
<dt>Action</dt>
<dt><span className="craik-fields__type">Receipt status</span></dt>
<dd>Notes</dd>
</div>

For persistent agents, a missing side-effect grant records `denial`
rather than upgrading the sandbox action to `passed`.

<div>
<dt><code>environment_decision</code></dt>
<dt><span className="craik-fields__type">passed</span></dt>
<dd>Routing decision recorded.</dd>
</div>

<div>
<dt><code>provider_action</code></dt>
<dt><span className="craik-fields__type">passed</span></dt>
<dd>Provider call recorded.</dd>
</div>

<div>
<dt><code>sandbox_action</code></dt>
<dt><span className="craik-fields__type">passed</span></dt>
<dd>Sandbox call recorded.</dd>
</div>

<div>
<dt><code>denial</code></dt>
<dt><span className="craik-fields__type">denied</span></dt>
<dd>Preserves the denial reason.</dd>
</div>

</div>

## Redaction

<div className="craik-keypoint">

**References, not raw payloads.**

Receipts store command references and target references — not raw
command strings, environment maps, SSH material, provider tokens, or
unredacted tool payloads.

</div>

Redacted fields include environment variables, credentials, command
payloads, raw commands, stdin, stdout, stderr, target payloads, and
secret-like metadata keys such as tokens, API keys, passwords, and
credentials.

## What's next

<div className="craik-next">

<a href="../sandbox-backends/">
<strong>Reference</strong>
<span>Sandbox backends</span>
<small>The contract every sandbox decision records against.</small>
</a>

<a href="../model-providers/">
<strong>Reference</strong>
<span>Model providers</span>
<small>The provider metadata the receipt links to.</small>
</a>

<a href="../../guides/provider-routing/">
<strong>Guide</strong>
<span>Provider routing &amp; sandboxes</span>
<small>The end-to-end routing flow these receipts back.</small>
</a>

</div>
