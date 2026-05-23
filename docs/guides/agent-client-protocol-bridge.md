# Agent Client Protocol Bridge

<p className="craik-meta"><span>3 min read</span><span>For integrators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

How v0.12.0 evaluates editor or client tool calls before they cross
into Craik runtime authority.

</div>

<div className="craik-keypoint">

**Clients route through Craik; they do not become policy.**

The bridge adapter rejects calls that lack operator authentication,
policy envelope context, capability grants, receipts, or redaction.
Client-provided instructions never outrank Craik policy.

</div>

## First Adapter

v0.12.0 ships `LocalAgentClientBridgeAdapter` for local protocol smoke
tests. It accepts an `AgentClientBridgeRequest`, runs
`decide_agent_client_bridge`, and returns:

<div className="craik-fields">

<div>
<dt>Decision</dt>
<dt><span className="craik-fields__type">Result</span></dt>
<dd>Meaning</dd>
</div>

<div><dt><code>allowed</code></dt><dt><span className="craik-fields__type">receipt emitted</span></dt><dd>The request had operator auth, policy envelope, capability grant, receipt, and redaction controls.</dd></div>
<div><dt><code>blocked</code></dt><dt><span className="craik-fields__type">no receipt</span></dt><dd>The request was missing a required control or attempted instruction/tool authority elevation.</dd></div>

</div>

## Required Controls

Every bridge request must include:

<ul>
<li>Operator subject from the active auth boundary.</li>
<li>Policy envelope id.</li>
<li>Capability grant id.</li>
<li>Redacted arguments and redacted output.</li>
<li>Receipt creation for allowed calls.</li>
</ul>

Write-effect requests also require operator approval. Missing approval
blocks the request before adapter output is produced.

## Prohibited Requests

The bridge blocks requests that:

<ul>
<li>Accept client instructions as authoritative over Craik policy.</li>
<li>Ask for unbounded tool access.</li>
<li>Send unredacted input or output.</li>
<li>Omit policy envelope or capability grant context.</li>
</ul>

## Validation

Run the bridge tests when changing protocol bridge decisions or adapter
receipt behavior:

```bash
uv run pytest tests/test_protocol_bridge.py
```

## What's Next

<div className="craik-next">

<a href="../../reference/adjacent-runtime-bridge/">
<strong>Reference</strong>
<span>Adjacent runtime bridge</span>
<small>The broader bridge decision model.</small>
</a>

<a href="../../reference/environment-receipts/">
<strong>Reference</strong>
<span>Environment receipts</span>
<small>How bridge actions become auditable evidence.</small>
</a>

<a href="../mcp-ecosystem-compatibility/">
<strong>Guide</strong>
<span>MCP ecosystem compatibility</span>
<small>Parallel policy rules for MCP tools and clients.</small>
</a>

</div>
