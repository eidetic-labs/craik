# MCP ecosystem compatibility

<p className="craik-meta"><span>5 min read</span><span>For integrators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The boundary for treating MCP servers, clients, tools, and resources
as policy-bound integration surfaces. MCP metadata can describe where
a service lives and what capability it offers, but it never bypasses
Craik capability grants, receipts, redaction, or operator approval.

</div>

<div className="craik-keypoint">

**Compatibility ≠ trust.**

Compatibility means Craik can represent the integration, route calls
through policy, and produce evidence and receipts. It does not mean
every external MCP server is trusted or enabled by default.

</div>

## Supported surfaces

<div className="craik-grid">

<div><h4>MCP client metadata</h4><p><a href="../../reference/mcp-client/">MCP client</a></p></div>
<div><h4>Exported memory &amp; context boundaries</h4><p><a href="../../reference/mcp-export-boundary/">MCP export boundary</a></p></div>
<div><h4>Runner &amp; tool routing</h4><p><a href="../../reference/runner-adapter-contract/">Runner adapter contract</a></p></div>
<div><h4>Plugin &amp; adapter examples</h4><p><a href="../../reference/reference-integrations/">Reference integrations</a></p></div>
<div><h4>Secret-safe configuration</h4><p><a href="../../reference/secret-migration-policy/">Secret migration policy</a></p></div>

</div>

## Clients and servers

<div className="craik-decision">

<div>
<h4>MCP clients store</h4>
<ul>
<li>Stable ids</li>
<li>Transport metadata</li>
<li>Command / endpoint references</li>
<li>Secret reference names</li>
<li>Policy envelope ids</li>
</ul>
</div>

<div>
<h4>MCP clients NEVER store</h4>
<ul>
<li>Raw bearer tokens</li>
<li>Passwords or private keys</li>
<li>Secret query strings</li>
</ul>
</div>

</div>

MCP servers are compatible when their advertised tools or resources
can be mapped to explicit Craik capabilities. A compatible server
still needs a capability grant before execution, and calls that affect
external systems produce receipts.

## Craik server mode

v0.12.0 adds a compatibility server surface for MCP smoke tests and
client integration. It exposes safe read surfaces first:

```bash
craik mcp server manifest
```

The manifest advertises read-only tools for case summaries, approved
memory search, and receipt metadata. Gated write tools are hidden by
default and only appear when explicitly requested:

```bash
craik mcp server manifest --include-write-tools
```

JSON-RPC compatibility handling is available for local integration
tests:

```bash
craik mcp server handle --request-json '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Tool calls map to Craik controls before execution. Read calls require
operator authentication. Write calls also require an approved policy
gate and receipt id. Denials are structured JSON-RPC errors with the
missing control listed in `error.data.required_controls`.

## Client config import/export

Import external MCP client config as redacted Craik metadata:

```bash
craik mcp client import --path ./mcp.json
```

The importer accepts both Craik-shaped `MCPClientConfig` JSON and
common `mcpServers` config objects. Environment variable names such as
`MCP_TOKEN` become `secret_ref_names`; raw values are not copied into
Craik config. Export prints the same clients in redacted form:

```bash
craik mcp client export --path ./mcp.json
```

Inside the terminal UI, `/mcp` reads configured MCP client metadata from
Craik local state and summarizes client ids, transports, advertised tool
counts, and stale config references. `/mcp verbose` expands each client with
grant, receipt, redaction, and tool-policy attributes. Add `--json` to either
form for structured output.

## Tools

A tool route is compatible when **every** condition holds:

<ol className="craik-steps">
<li>The requested capability is represented in policy.</li>
<li>The route requires a grant where policy requires one.</li>
<li>Input and output can be redacted before public reporting.</li>
<li>Execution receipts can name the tool, route, policy envelope, and result.</li>
<li>Failures can be reported without exposing credentials or private local paths.</li>
</ol>

Tools that cannot be represented with these controls remain
unsupported until an adapter adds the missing policy, receipt, or
redaction behavior.

## Resources

MCP resources are compatible as read surfaces when Craik can attach
provenance, scope, and redaction behavior. Resource reads become
evidence references or bounded context inputs — never unreviewed
durable memory writes.

Resource content containing secrets, private task names, local paths,
or operator-only data must be redacted before appearing in public
docs, receipts, or export artifacts.

## Exports and adapters

Exports preserve the same boundaries used at runtime.

<div className="craik-grid">

<div><h4>Policy envelopes</h4><p>Identify the rules that governed an export.</p></div>
<div><h4>Capability grants</h4><p>Identify the authority used by an adapter.</p></div>
<div><h4>Receipts</h4><p>Identify actions taken and checks performed.</p></div>
<div><h4>Redaction markers</h4><p>Replace sensitive values.</p></div>
<div><h4>Secret references</h4><p>Remain references, not copied values.</p></div>

</div>

Adapters may translate between MCP schemas and Craik contracts, but
they must not collapse policy decisions into plain-text notes. If a
source integration cannot preserve capability grants, receipts, or
redaction outcomes, the adapter marks that surface as unsupported or
requires operator review.

## Unsupported surfaces

<div className="craik-keypoint">

**Boundaries Craik does not treat as compatible.**

</div>

<div className="craik-grid">

<div><h4>Importing raw server secrets</h4><p>Into Craik config.</p></div>
<div><h4>Executing tools without grants</h4><p>When policy requires one.</p></div>
<div><h4>Exporting unredacted I/O</h4><p>Or resource bodies.</p></div>
<div><h4>Resource reads as memory writes</h4><p>Automatic durable writes are unsupported.</p></div>
<div><h4>Server-provided instructions</h4><p>Higher priority than project, operator, or policy instructions.</p></div>
<div><h4>Tool success without receipts</h4><p>When policy requires receipts.</p></div>

</div>

## Compatibility checklist

<ol className="craik-steps">
<li>The client or adapter is represented by a stable id.</li>
<li>Command, endpoint, and secret values are references — not raw secrets.</li>
<li>Every tool route maps to an explicit capability.</li>
<li>Required grants and receipts are configured.</li>
<li>Public reporting paths apply redaction.</li>
<li>Unsupported fields are documented with migration or adapter notes.</li>
<li>Dry runs and compatibility reports avoid private paths, credentials, and private task names.</li>
</ol>

## What's next

<div className="craik-next">

<a href="../../reference/mcp-client/">
<strong>Reference</strong>
<span>MCP client</span>
<small>The client-side metadata contract.</small>
</a>

<a href="../../reference/mcp-export-boundary/">
<strong>Reference</strong>
<span>MCP export boundary</span>
<small>Which Craik surfaces can be exported as MCP tools.</small>
</a>

<a href="../provider-routing/">
<strong>Guide</strong>
<span>Provider routing &amp; sandboxes</span>
<small>How MCP fits into the broader routing flow.</small>
</a>

</div>
