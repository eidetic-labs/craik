# MCP export boundary

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The rule for which Craik surfaces can be exported as MCP tools.
Stable, documented metadata and workflow surfaces can be exported.
Unstable internals, raw store internals, and secret-bearing operations
cannot.

</div>

<div className="craik-keypoint">

**Contract-first exports.**

Exported tools wrap stable runtime contracts and documented command
behavior — never private Python objects or database tables.

</div>

## Export criteria

A surface is **exportable** when every condition holds.

<ol className="craik-steps">
<li>It has a stable contract and documented compatibility expectations.</li>
<li>It does not expose raw secrets, tokens, credentials, signatures, or unredacted payloads.</li>
<li>It does not expose internal storage layouts, private state machines, or unstable implementation details.</li>
<li>It uses explicit capability grants for capability-bearing tools.</li>
<li>It records receipts for side-effect capabilities (file writes · shell · network · memory writes · review comments).</li>
<li>It returns redacted metadata rather than ambient runtime authority.</li>
</ol>

Experimental surfaces require compatibility review before export.
Internal surfaces are blocked until promoted to a stable contract.

## Chosen boundary

<div className="craik-decision">

<div>
<h4>Allowed</h4>
<ul>
<li>Read-only project, case file, handoff, receipt, and work-graph inspection</li>
<li>Provider selection metadata that omits secret values</li>
<li>Policy preview and validation results</li>
<li>Documented runner or gateway status summaries</li>
</ul>
</div>

<div>
<h4>Blocked</h4>
<ul>
<li>Raw secret reads or secret-file browsing</li>
<li>Direct local-store table access</li>
<li>Write / shell / network / memory-write / review-comment tools without matching grants and receipts</li>
<li>Experimental sandbox or provider internals without compatibility review</li>
</ul>
</div>

</div>

## Compatibility expectations

<div className="craik-keypoint">

**Names, inputs, outputs, and error reasons are compatibility surface.**

Changes should be additive where possible. Removing a field, changing
a status value, or exposing a previously redacted field requires
review and documentation updates.

</div>

<div className="craik-fields">

<div>
<dt>Decision</dt>
<dt><span className="craik-fields__type">Meaning</span></dt>
<dd>Required action</dd>
</div>

<div>
<dt><code>review_required</code></dt>
<dt><span className="craik-fields__type">non-exportable</span></dt>
<dd>Treat as non-exportable until a human or release process promotes the surface.</dd>
</div>

<div>
<dt><code>blocked</code></dt>
<dt><span className="craik-fields__type">unsupported</span></dt>
<dd>Requires a boundary change before export.</dd>
</div>

</div>

The `craik.runtime.mcp_export` helper records the decision status,
reason, and required controls for a candidate surface. The v0.12.0
`craik.runtime.sandbox.mcp_compat` helper applies those decisions to
the MCP compatibility manifest and JSON-RPC smoke handler. It does not
grant runtime authority by itself; tool calls still pass through
operator auth, policy gates, and receipt requirements.

## What's next

<div className="craik-next">

<a href="../mcp-client/">
<strong>Reference</strong>
<span>MCP client</span>
<small>Client-side provider and tool routing.</small>
</a>

<a href="../../guides/mcp-ecosystem-compatibility/">
<strong>Guide</strong>
<span>MCP ecosystem compatibility</span>
<small>How to compose Craik with the wider MCP ecosystem.</small>
</a>

<a href="../environment-receipts/">
<strong>Reference</strong>
<span>Environment receipts</span>
<small>The audit trail an exported tool produces.</small>
</a>

</div>
