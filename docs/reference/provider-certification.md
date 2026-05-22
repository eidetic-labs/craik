# Provider certification

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The certification bar OpenAI, Anthropic, and Gemini must clear before
they ship as governed provider paths — requirements, families, the
implementation boundary, and the deterministic test posture.

</div>

<div className="craik-keypoint">

**Design rationale: [ADR 0002 · Provider transport and mode families](../adr/0002-provider-transport-and-mode-families.md).**

Provider metadata alone is not enough. A provider is MVP-ready only
when tests and receipts show the runtime can safely use it in a
governed workflow.

</div>

## MVP requirements

Each certified provider path must cover:

<div className="craik-grid">

<div><h4>Chat</h4></div>
<div><h4>Streaming</h4></div>
<div><h4>Tool calls</h4></div>
<div><h4>Structured output</h4></div>
<div><h4>Usage metadata</h4></div>
<div><h4>Retryable errors</h4></div>
<div><h4>Redaction</h4></div>
<div><h4>Receipts</h4></div>

</div>

<div className="craik-keypoint">

**Certification gate.**

<code>ProviderCertification</code> records provider family · model
references · requirements that passed · requirements that are blocked
· policy envelope · evidence · receipts · documentation reference.
<code>provider_certification_decision</code> returns
<code>certified</code> only when every MVP requirement is supported
and none is blocked.

</div>

## Provider families

<div className="craik-fields">

<div>
<dt>Family</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>openai</code></dt>
<dt><span className="craik-fields__type">MVP</span></dt>
<dd>Uses secret references for API credentials.</dd>
</div>

<div>
<dt><code>anthropic</code></dt>
<dt><span className="craik-fields__type">MVP</span></dt>
<dd>Uses secret references for API credentials.</dd>
</div>

<div>
<dt><code>gemini</code></dt>
<dt><span className="craik-fields__type">v0.9.0</span></dt>
<dd>Uses secret references for API credentials and Gemini-specific request normalization.</dd>
</div>

</div>

Public metadata, receipts, docs, and certification fixtures must not
include raw API keys, organization secrets, request bodies containing
private task text, or provider console credentials.

## Implementation boundary

<div className="craik-keypoint">

**Verify first, then implement.**

Before implementing live API behavior, provider-specific assumptions
should be verified against official provider documentation.
Certification tests remain deterministic by default and use fixtures
unless a live smoke profile is explicitly enabled.

</div>

## MVP runtime certification

Deterministic tests against
`craik.runtime.providers.provider_runtime` certify both OpenAI and
Anthropic, while `craik.runtime.providers.provider_runtime_gemini`
certifies Gemini for:

<div className="craik-grid">

<div><h4>Request payload construction</h4><p>Chat · streaming · tools · structured output.</p></div>
<div><h4>Response normalization</h4><p>Text · tool calls · structured output · response ids · usage metadata.</p></div>
<div><h4>Retry decisions</h4><p>Throttling · transient failures · overloads.</p></div>
<div><h4>Secret-reference-only configuration</h4></div>
<div><h4>Redacted provider receipts</h4></div>
<div><h4>Explicit live-access gating</h4></div>

</div>

Live provider calls remain disabled unless a caller constructs an
adapter with `live_enabled=true` and supplies credentials through an
external secret resolver.

## Official provider references

<div className="craik-fields">

<div>
<dt>Family</dt>
<dt><span className="craik-fields__type">Docs verified for</span></dt>
<dd>Surfaces</dd>
</div>

<div>
<dt>OpenAI</dt>
<dt><span className="craik-fields__type">official</span></dt>
<dd>Responses · streaming · structured outputs · function calling · models.</dd>
</div>

<div>
<dt>Anthropic</dt>
<dt><span className="craik-fields__type">official</span></dt>
<dd>Messages · streaming · tool use · model names · rate limits.</dd>
</div>

<div>
<dt>Gemini</dt>
<dt><span className="craik-fields__type">official</span></dt>
<dd>generateContent · function calling · structured output · model names.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../model-providers/">
<strong>Reference</strong>
<span>Model providers</span>
<small>The registry and the budget/quota gating.</small>
</a>

<a href="../../adr/provider-transport-and-mode-families/">
<strong>ADR</strong>
<span>0002 · Provider transport</span>
<small>The family/transport split this certification rests on.</small>
</a>

<a href="../provider-failover/">
<strong>Reference</strong>
<span>Provider failover</span>
<small>How fallback rules compose with certified providers.</small>
</a>

</div>
