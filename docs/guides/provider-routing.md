# Provider routing and sandboxes

<p className="craik-meta"><span>5 min read</span><span>For operators &amp; integrators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Walk through provider selection, budget/quota gating, failover,
optional MCP routing, sandbox selection, and the environment receipts
that record each decision. Provider and sandbox routing are kept
separate so policy can audit each boundary independently.

</div>

<div className="craik-keypoint">

**Two independent decisions.**

Provider routing chooses model/runtime metadata. Sandbox routing
chooses an execution environment. Keeping them separate lets policy,
receipts, and redaction audit each boundary on its own terms.

</div>

## Routing flow

<ol className="craik-steps">
<li>Select a model provider from <a href="../../reference/model-providers/">Model providers</a>.</li>
<li>Check provider budget and quota before dispatch.</li>
<li>Evaluate <a href="../../reference/provider-failover/">provider failover</a> only when a configured fallback rule allows it.</li>
<li>Use <a href="../../reference/mcp-client/">MCP client</a> metadata for provider or tool routes that cross an MCP boundary.</li>
<li>Select a <a href="../../reference/sandbox-backends/">sandbox backend</a> for execution.</li>
<li>Record <a href="../../reference/environment-receipts/">environment receipts</a> for allowed and denied provider or sandbox decisions.</li>
</ol>

## Provider configuration

<div className="craik-grid">

<div><h4>Provider id · family · modes · capabilities</h4></div>
<div><h4>Trust boundary</h4></div>
<div><h4>Config reference names</h4></div>
<div><h4>Secret reference names</h4></div>
<div><h4>Budget and quota refs</h4></div>
<div><h4>Runtime path</h4></div>
<div><h4>Docs links</h4></div>

</div>

## Local model routing

Local model presets are provider records with a local trust boundary
and no secret references by default. Use them when the model server is
OpenAI-compatible and reachable on loopback:

<div className="craik-grid">

<div><h4><code>provider_local_openai_compatible</code></h4><p>Generic local OpenAI-compatible endpoint.</p></div>
<div><h4><code>provider_local_ollama</code></h4><p>Ollama OpenAI-compatible endpoint.</p></div>
<div><h4><code>provider_local_lm_studio</code></h4><p>LM Studio local server.</p></div>
<div><h4><code>provider_local_vllm</code></h4><p>vLLM OpenAI-compatible server.</p></div>

</div>

Run `craik provider local-presets` to inspect preset metadata and
`craik provider local-health <preset>` to check `/v1/models` before
enabling live local routing. Local HTTP URLs must remain loopback
unless a future sandbox policy explicitly allows a wider boundary.

<div className="craik-keypoint">

**Secrets are references, not values.**

Secret values never appear in provider records, CLI output, docs,
receipts, or fixtures. Store raw credentials outside Craik and refer
to them by secret reference name.

</div>

## MCP integration

<div className="craik-decision">

<div>
<h4><a href="../../reference/mcp-export-boundary/">MCP export boundary</a></h4>
<p>Decide which Craik surfaces can be exported as MCP tools.</p>
</div>

<div>
<h4><a href="../../reference/mcp-client/">MCP client</a></h4>
<p>Client-side provider and tool routing.</p>
</div>

</div>

MCP routes must remain:

<div className="craik-grid">

<div><h4>Grant-required</h4></div>
<div><h4>Receipt-required</h4></div>
<div><h4>Redacted</h4></div>
<div><h4>Documented</h4><p>When part of the compatibility surface.</p></div>

</div>

## Sandbox backends

The v0.9.0 sandbox surfaces:

<div className="craik-grid">

<div><h4><a href="../../reference/local-process-backend/">Local process</a></h4></div>
<div><h4><a href="../../reference/remote-shell-backend/">Remote shell</a></h4></div>
<div><h4><a href="../../reference/browser-tool-boundary/">Browser tool boundary</a></h4></div>
<div><h4><a href="../../reference/docker-sandbox-backend/">Docker sandbox</a></h4></div>

</div>

<div className="craik-keypoint">

**Policy, grants, receipts, redaction — every backend.**

All sandbox actions require explicit policy, capability grants,
receipts, and redaction. Local and remote shell helpers use command
references instead of inline shell strings. Docker requests require
explicit network, mount, image, command, and environment references.
Browser/tool results are redacted before receipt metadata is persisted.

</div>

## Safe diagnostics

<div className="craik-fields">

<div>
<dt>Command</dt>
<dt><span className="craik-fields__type">Output</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>craik provider list</code></dt>
<dt><span className="craik-fields__type">JSON metadata</span></dt>
<dd>Provider ids · modes · capabilities · trust boundaries · config refs · secret reference names · budget refs · quota refs · docs. Secret values are not printed.</dd>
</div>

<div>
<dt><code>craik provider show &lt;id&gt;</code></dt>
<dt><span className="craik-fields__type">one record</span></dt>
<dd>Missing provider ids return a clear CLI error.</dd>
</div>

<div>
<dt><code>craik provider select &lt;id&gt; --mode runner --policy-envelope-id &lt;id&gt;</code></dt>
<dt><span className="craik-fields__type">redacted selection</span></dt>
<dd>Returns provider metadata · budget &amp; quota refs · policy envelope id · receipt ids. Does NOT call a provider, load credentials, or grant execution authority.</dd>
</div>

<div>
<dt><code>craik demo persistent-agent --repo-path .</code></dt>
<dt><span className="craik-fields__type">fixture e2e</span></dt>
<dd>Launches persistent sessions, runs provider prompts, records receipts and handoffs, and inspects final session state without live model calls.</dd>
</div>

</div>

## Validation

```sh
uv run --extra dev pytest tests/test_model_providers.py tests/test_mcp_client.py tests/test_sandbox_backend.py tests/test_environment_receipts.py
```

Expected output: passing tests for provider metadata, MCP client
routing, sandbox backend contracts, and environment receipts.

```sh
uv run --extra dev pytest tests/test_sandbox_policy_boundaries.py
```

Expected output: passing tests for allowed sandbox actions, denied
missing-policy controls, denied unsafe isolation defaults, and
redacted environment receipts.

<div className="craik-keypoint">

**Public boundary.**

Do not include local filesystem paths, private hostnames, raw command
payloads, environment maps, webhook secrets, bearer tokens, SSH keys,
provider credentials, or unredacted tool outputs in public docs. Use
stable fixture ids, config refs, and secret reference names instead.

</div>

## What's next

<div className="craik-next">

<a href="../../reference/model-providers/">
<strong>Reference</strong>
<span>Model providers</span>
<small>The shipped provider metadata catalog.</small>
</a>

<a href="../../reference/sandbox-backends/">
<strong>Reference</strong>
<span>Sandbox backends</span>
<small>The full sandbox-contract surface.</small>
</a>

<a href="../../reference/environment-receipts/">
<strong>Reference</strong>
<span>Environment receipts</span>
<small>The audit trail produced by every routing decision.</small>
</a>

</div>
