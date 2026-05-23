# Adjacent runtime bridge

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The rule for bridging to adjacent runtimes — posture levels, required
controls, and prohibited behavior.

</div>

<div className="craik-keypoint">

**Bridge routes, doesn't elevate.**

A bridge may route work to another runtime, but it must not turn that
runtime into a source of higher-priority instructions or unbounded
tool authority.

</div>

## Posture

`adjacent_runtime_bridge_decision` returns `allowed`,
`review_required`, `deferred`, or `blocked` for a candidate surface.

<div className="craik-fields">

<div>
<dt>Level</dt>
<dt><span className="craik-fields__type">Use</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>supported</code></dt>
<dt><span className="craik-fields__type">allowed</span></dt>
<dd>When all required controls are present.</dd>
</div>

<div>
<dt><code>experimental</code></dt>
<dt><span className="craik-fields__type">review required</span></dt>
<dd>Controls may be defined but explicit review required before use.</dd>
</div>

<div>
<dt><code>deferred</code></dt>
<dt><span className="craik-fields__type">unavailable</span></dt>
<dd>Remains unavailable until a later product decision, even with controls.</dd>
</div>

</div>

## Required controls

<div className="craik-grid">

<div><h4>Policy envelope id</h4></div>
<div><h4>Preserved policy context</h4></div>
<div><h4>Preserved evidence links</h4></div>
<div><h4>Explicit capability grants</h4></div>
<div><h4>Execution receipts</h4></div>
<div><h4>Input &amp; output redaction</h4></div>
<div><h4>Documented decision</h4><p>When exposed as supported integration.</p></div>

</div>

## Prohibited behavior

Adjacent runtime bridges are **blocked** when they:

<div className="craik-grid">

<div><h4>Copy secret values</h4></div>
<div><h4>Grant unbounded tool access</h4></div>
<div><h4>Accept external instructions as authoritative</h4><p>Over Craik policy.</p></div>
<div><h4>Mutate state without operator approval</h4></div>
<div><h4>Omit policy envelope context</h4></div>
<div><h4>Omit grants / receipts / evidence / redaction</h4></div>

</div>

<div className="craik-keypoint">

**Bridge receipts identify everything.**

Runtime · route · policy envelope · evidence links · capability grant ·
redaction outcome · operator approval (when a mutation is requested).

</div>

## v0.12.0 Agent/Client Bridge

`craik.runtime.agents.protocol_bridge` implements the first local
agent/client protocol bridge adapter. It is designed for editor and
client smoke tests, not for granting ambient runtime authority.

`AgentClientBridgeRequest` records the client name, requested tool,
capability, operator subject, policy envelope, capability grant,
evidence links, and redacted arguments. `decide_agent_client_bridge`
blocks requests that lack operator auth, policy context, grants,
receipts, or redaction. It also blocks client-provided authoritative
instructions and unbounded tool access.

`LocalAgentClientBridgeAdapter` emits a redacted
`craik.capability_receipt` for allowed calls. Blocked calls return a
structured decision and no receipt.

## What's next

<div className="craik-next">

<a href="../multi-agent-workflow-bridge/">
<strong>Reference</strong>
<span>Multi-agent workflow bridge</span>
<small>The companion contract for external coordination systems.</small>
</a>

<a href="../adjacent-tool-migration/">
<strong>Reference</strong>
<span>Adjacent-tool migration</span>
<small>The assessment that precedes a bridge.</small>
</a>

<a href="../mcp-export-boundary/">
<strong>Reference</strong>
<span>MCP export boundary</span>
<small>The parallel boundary for tool-export decisions.</small>
</a>

</div>
