# MCP client

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The MCP-client metadata contract Craik uses for provider and tool
routing across an MCP boundary — what it records, the route shape, and
the audit boundary.

</div>

<div className="craik-keypoint">

**Metadata, not a secret store.**

Craik MCP client configuration is metadata for routing. It does not
grant runtime authority by itself.

</div>

## What it records

`craik.runtime.mcp_client.MCPClientConfig` records:

<div className="craik-grid">

<div><h4>Stable client id and name</h4></div>
<div><h4>Transport</h4><p><code>stdio</code> · <code>http</code> · <code>sse</code>.</p></div>
<div><h4>Non-secret server/endpoint/command/config refs</h4></div>
<div><h4>Secret reference names</h4></div>
<div><h4>Policy envelope id</h4><p>When the client is bound to a policy.</p></div>
<div><h4>Grant · receipt · redaction requirements</h4></div>
<div><h4>Docs &amp; non-secret metadata</h4></div>

</div>

<div className="craik-fields">

<div>
<dt>Transport</dt>
<dt><span className="craik-fields__type">Requires</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>http</code> · <code>sse</code></dt>
<dt><span className="craik-fields__type"><code>endpoint_ref</code></span></dt>
<dd>Endpoint reference, never a raw URL with embedded secrets.</dd>
</div>

<div>
<dt><code>stdio</code></dt>
<dt><span className="craik-fields__type"><code>command_ref</code></span></dt>
<dd>Command reference for subprocess transport.</dd>
</div>

</div>

<div className="craik-keypoint">

**No embedded credentials.**

Endpoint and command refs are references or configured names — never
raw credentials, bearer tokens, API keys, passwords, or secret query
values.

</div>

## Routes

`MCPClientRoute` links a client to either a provider route or a tool
route.

<div className="craik-grid">

<div><h4>Route id</h4></div>
<div><h4>Client id</h4></div>
<div><h4>Route kind</h4><p><code>provider</code> or <code>tool</code>.</p></div>
<div><h4>Target reference</h4><p>Provider id or tool name.</p></div>
<div><h4>Required capability</h4></div>
<div><h4>Grant + receipt required?</h4></div>

</div>

Routes are compatible only when they belong to the selected client and
remain grant- and receipt-required.

## Import/export

`craik mcp client import --path ./mcp.json` accepts either a
Craik-shaped `MCPClientConfig` object or an external `mcpServers`
object. Imported config is redacted before printing:

<div className="craik-grid">

<div><h4>Command transport</h4><p><code>command</code> becomes <code>command_ref</code>; non-secret args become <code>config_refs</code>.</p></div>
<div><h4>HTTP transport</h4><p><code>url</code> becomes <code>endpoint_ref</code>.</p></div>
<div><h4>Environment secrets</h4><p>Secret-like env var names become <code>secret_ref_names</code>; values are not copied.</p></div>
<div><h4>Metadata</h4><p>Secret-like metadata values are replaced before export.</p></div>

</div>

`craik mcp client export --path ./mcp.json` emits redacted client
metadata for review or migration evidence.

## Audit boundary

<div className="craik-keypoint">

**Receipt-ready before dispatch.**

Compatibility checks return route ids, required controls, and reasons
for blocked routes so callers can write audit records through the
normal receipt workflow. Raw endpoint secrets, bearer tokens, and
credentials stay outside Craik configuration — referenced by name only.

</div>

## What's next

<div className="craik-next">

<a href="../mcp-export-boundary/">
<strong>Reference</strong>
<span>MCP export boundary</span>
<small>Which Craik surfaces can be exported as MCP tools.</small>
</a>

<a href="../../guides/mcp-ecosystem-compatibility/">
<strong>Guide</strong>
<span>MCP ecosystem compatibility</span>
<small>Compatibility expectations and unsupported behavior.</small>
</a>

<a href="../../guides/provider-routing/">
<strong>Guide</strong>
<span>Provider routing &amp; sandboxes</span>
<small>How MCP fits into the broader routing flow.</small>
</a>

</div>
