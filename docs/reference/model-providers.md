# Model providers

<p className="craik-meta"><span>4 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.model_provider` contract — what it records, the secret
boundary, the registry, the provider runtime adapters (OpenAI,
Anthropic, Gemini, and OpenAI-compatible local models), the
provider-backed runner path, and budget/quota gating.

</div>

<div className="craik-keypoint">

**Design rationale: [ADR 0002 · Provider transport and mode families](../adr/0002-provider-transport-and-mode-families.md).**

</div>

## What it records

<div className="craik-grid">

<div><h4>Stable provider id</h4></div>
<div><h4>Provider name</h4></div>
<div><h4>Provider family</h4></div>
<div><h4>Supported modes</h4><p><code>chat</code> · <code>completion</code> · <code>embedding</code> · <code>tool</code> · <code>runner</code>.</p></div>
<div><h4>Capability declarations</h4></div>
<div><h4>Trust boundary</h4></div>
<div><h4>Non-secret config references</h4></div>
<div><h4>Secret reference names</h4></div>
<div><h4>Budget &amp; quota reference names</h4></div>
<div><h4>Optional runtime path</h4></div>
<div><h4>Docs links</h4></div>

</div>

## Secret boundary

<div className="craik-keypoint">

**References, not values.**

Provider metadata must not contain secret-like keys such as API keys,
tokens, passwords, credentials, or secrets. Public provider records
may name secret references but must not include secret values.

</div>

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Stores</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>config_refs</code></dt>
<dt><span className="craik-fields__type">references</span></dt>
<dd>Non-secret configuration names.</dd>
</div>

<div>
<dt><code>secret_ref_names</code></dt>
<dt><span className="craik-fields__type">references</span></dt>
<dd>External secret handles.</dd>
</div>

<div>
<dt><code>budget_ref</code> · <code>quota_ref</code></dt>
<dt><span className="craik-fields__type">references</span></dt>
<dd>Non-secret budget and quota handles. Never billing credentials.</dd>
</div>

</div>

## Registry

`craik.runtime.providers.model_providers.ModelProviderRegistry`
provides in-memory registration and lookup by stable provider id.
Duplicate provider ids are rejected. Missing providers raise a clear
lookup error.

<div className="craik-keypoint">

**Metadata-only.**

The registry does not call providers, load credentials, or grant
execution authority by itself.

</div>

Built-in providers:

<div className="craik-fields">

<div>
<dt>Provider</dt>
<dt><span className="craik-fields__type">Path</span></dt>
<dd>Use for</dd>
</div>

<div>
<dt><code>provider_fixture_local</code></dt>
<dt><span className="craik-fields__type">deterministic</span></dt>
<dd>Local workflows and tests.</dd>
</div>

<div>
<dt><code>provider_openai</code></dt>
<dt><span className="craik-fields__type">third-party</span></dt>
<dd>OpenAI Responses API-compatible MVP execution.</dd>
</div>

<div>
<dt><code>provider_anthropic</code></dt>
<dt><span className="craik-fields__type">third-party</span></dt>
<dd>Anthropic Messages API-compatible MVP execution.</dd>
</div>

<div>
<dt><code>provider_gemini</code></dt>
<dt><span className="craik-fields__type">third-party</span></dt>
<dd>Gemini generateContent API-compatible v0.9.0 execution.</dd>
</div>

<div>
<dt><code>provider_local_openai_compatible</code></dt>
<dt><span className="craik-fields__type">local</span></dt>
<dd>Local OpenAI-compatible chat completions execution.</dd>
</div>

</div>

OpenAI, Anthropic, and Gemini records use third-party trust
boundaries, external secret references, budget and quota references,
and runtime adapter paths under
`craik.runtime.providers.provider_runtime`. Default model metadata is
non-secret and may be overridden by named configuration references
before live use.

## Provider runtime

`craik.runtime.providers.provider_runtime` defines the
provider-neutral request, result, adapter, retry decision, and receipt
helpers used by the MVP provider path.

<div className="craik-decision">

<div>
<h4>OpenAI adapter</h4>
<ul>
<li>System messages → developer messages</li>
<li><code>stream</code> passthrough</li>
<li>Function tools with strict JSON schemas</li>
<li>Structured output via <code>text.format</code></li>
<li>Normalized usage metadata + tool calls</li>
</ul>
</div>

<div>
<h4>Anthropic adapter</h4>
<ul>
<li>Top-level system instructions</li>
<li>User &amp; assistant messages in the message list</li>
<li><code>stream</code> passthrough</li>
<li>Client tools with <code>input_schema</code></li>
<li>Structured output as a forced client tool</li>
<li>Normalized usage metadata + tool calls</li>
</ul>
</div>

<div>
<h4>Gemini adapter</h4>
<ul>
<li>System instructions via <code>systemInstruction</code></li>
<li>User and model turns via <code>contents</code></li>
<li>Function declarations through Gemini tools</li>
<li>Structured output through <code>generationConfig.responseSchema</code></li>
<li>Normalized usage metadata + function calls</li>
</ul>
</div>

<div>
<h4>Local adapter</h4>
<ul>
<li>OpenAI-compatible chat completions payloads</li>
<li>Optional marker/no-secret local operation</li>
<li>Loopback URLs only when explicitly allowed</li>
</ul>
</div>

</div>

Adapters classify retryable API conditions and gate live access
behind an explicit `live_enabled=true` runtime setting. **Deterministic
tests use fixtures and normalized payloads; they do not contact live
providers.**

## Provider-backed runner path

`craik.runtime.provider_runner` connects the provider runtime to the
governed single-agent loop.

<ol className="craik-steps">
<li>Build or load the task case file.</li>
<li>Compile a provider-runner prompt from the case file and policy envelope.</li>
<li>Execute the loop through a certified provider id such as <code>provider_openai</code>, <code>provider_anthropic</code>, or <code>provider_gemini</code>.</li>
<li>Record provider receipts for every model step.</li>
<li>Preserve side-effect receipts from the loop.</li>
<li>Persist normalized run outputs.</li>
<li>Create a durable handoff for completed / blocked / failed / interrupted outcomes.</li>
</ol>

<div className="craik-keypoint">

**Deterministic by default.**

The default provider-backed path certifies Craik handoff, receipt, and
output plumbing without contacting live APIs. Live provider transport
must be enabled explicitly by future caller configuration.

</div>

## Budget and quota checks

`craik.runtime.provider_budgets` evaluates non-secret provider budget
status before routing. Routing is **blocked** when:

<div className="craik-grid">

<div><h4>Status belongs to a different provider</h4></div>
<div><h4>Status is explicitly blocked</h4></div>
<div><h4>Remaining budget is zero or below</h4></div>
<div><h4>Remaining quota is zero or below</h4></div>

</div>

Allowed decisions preserve provider id, budget ref, quota ref, and
remaining budget/quota values for later receipts.

## Official docs verified

Provider assumptions for the runtime were checked against official
provider docs:

<div className="craik-grid">

<div><h4>OpenAI</h4><p>Responses API · streaming responses · structured outputs · function calling · model docs.</p></div>
<div><h4>Anthropic</h4><p>Messages API · streaming messages · tool use · model overview · rate limit docs.</p></div>
<div><h4>Gemini</h4><p>generateContent · function calling · structured output · model docs. Verified 2026-05-22.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../../adr/provider-transport-and-mode-families/">
<strong>ADR</strong>
<span>0002 · Provider transport &amp; mode families</span>
<small>Design rationale for the family/transport split.</small>
</a>

<a href="../../guides/provider-routing/">
<strong>Guide</strong>
<span>Provider routing &amp; sandboxes</span>
<small>End-to-end routing flow.</small>
</a>

<a href="../provider-failover/">
<strong>Reference</strong>
<span>Provider failover</span>
<small>How fallback rules compose with budgets.</small>
</a>

</div>
