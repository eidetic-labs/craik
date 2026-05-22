# Webhook ingress

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The validation boundary for one webhook request — signature checks,
payload-size checks, JSON parsing, timestamp freshness, event-id
idempotency, event-type authorization, replay protection, and redacted
ingress receipts.

</div>

<div className="craik-keypoint">

**Validation, not authority.**

Webhook validation does not grant channel authority. Accepted events
still need channel policy, allowlist, identity, and capability checks
before any privileged gateway action.

</div>

## What it provides

`craik.runtime.webhook_ingress` covers:

<div className="craik-grid">

<div><h4>HMAC SHA-256 signature validation</h4></div>
<div><h4>Payload size cap</h4><p>Oversized bodies are rejected before parsing.</p></div>
<div><h4>JSON object parsing</h4></div>
<div><h4>JSON nesting-depth limit</h4></div>
<div><h4>Required <code>event_id</code> &amp; <code>event_type</code> extraction</h4></div>
<div><h4>Timestamp freshness</h4><p>Events outside the allowed window are rejected.</p></div>
<div><h4>Idempotency checks</h4><p>Against known and persisted event ids.</p></div>
<div><h4>Event-type authorization</h4></div>
<div><h4>Redacted ingress receipts</h4></div>

</div>

## Signature

Requests use one `X-Craik-Signature` header. Header names are handled
case-insensitively, and ambiguous duplicate signature headers fail
closed.

```text
sha256=<hex digest>
```

The digest is computed over the raw request body with the configured
webhook secret. Missing or invalid signatures are rejected before JSON
parsing.

## Event shape

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Required</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>event_id</code></dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Duplicate ids are rejected before dispatch.</dd>
</div>

<div>
<dt><code>event_type</code></dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Only configured event types are accepted.</dd>
</div>

<div>
<dt><code>timestamp</code></dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Must be inside the configured freshness window.</dd>
</div>

<div>
<dt><code>payload</code></dt>
<dt><span className="craik-fields__type">optional object</span></dt>
<dd>Application-specific.</dd>
</div>

</div>

## Safe dispatch

Accepted results include a `dispatch_payload` containing the event id,
event type, and object payload. **The helper does not perform side
effects or enqueue work by itself.**

## Receipts

Webhook ingress receipts use the `webhook.ingress` capability. Receipt
metadata preserves event id, event type, policy envelope id, ingress
status, and redaction fields. **Raw body, signatures, and payload
content are not stored in receipt metadata.**

## What's next

<div className="craik-next">

<a href="../gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>The receipt shape ingress produces.</small>
</a>

<a href="../channel-policy-envelopes/">
<strong>Reference</strong>
<span>Channel policy envelopes</span>
<small>The next stage in the gateway pipeline.</small>
</a>

<a href="../../guides/gateway-troubleshooting/">
<strong>Guide</strong>
<span>Gateway troubleshooting</span>
<small>Diagnose webhook failures.</small>
</a>

</div>
