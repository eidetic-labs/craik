# Channel adapter contract

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The boundary contract for external operator ingress through always-on
gateway channels — adapter identity, capabilities, inbound/outbound
shapes, receipts, and trust boundaries.

</div>

<div className="craik-keypoint">

**Descriptive, not authorizing.**

The contract validates and inspects channel adapter identity, payload
shape, capabilities, receipts, and trust boundaries before a specific
adapter is wired into the gateway.

</div>

## Identity

<div className="craik-grid">

<div><h4>Stable adapter id</h4></div>
<div><h4>Channel kind</h4><p><code>messaging</code> · <code>webhook</code> · <code>scheduler</code> · <code>voice</code> · <code>custom</code>.</p></div>
<div><h4>Human-readable name</h4></div>
<div><h4>Adapter version</h4></div>
<div><h4>Optional external service name</h4></div>

</div>

Identity is not authorization. It only identifies the adapter
implementation and channel family.

## Capabilities

Each capability declares:

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Values</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Direction</dt>
<dt><span className="craik-fields__type">inbound / outbound / bidirectional</span></dt>
<dd>How traffic flows.</dd>
</div>

<div>
<dt>Description</dt>
<dt><span className="craik-fields__type">prose</span></dt>
<dd>What the capability does.</dd>
</div>

<div>
<dt>Grant required?</dt>
<dt><span className="craik-fields__type">bool</span></dt>
<dd>Most capabilities require a grant.</dd>
</div>

<div>
<dt>Receipt required?</dt>
<dt><span className="craik-fields__type">bool</span></dt>
<dd>Most capabilities require a receipt.</dd>
</div>

</div>

<div className="craik-keypoint">

**No ambient authority.**

Channel capabilities are still governed by policy envelopes and
explicit grants. Adapters do not receive ambient authority from being
installed or configured.

</div>

## Inbound events

Required fields: `event_id` · `channel` · `received_at` · `sender`.

Adapters may include additional normalized fields such as `text`,
`thread_id`, or channel-specific metadata. Sensitive payload fields
should be listed in `redacted_fields`.

## Outbound responses

Required fields: `status` · `summary`.

Adapters may include delivery metadata, response ids, text bodies,
receipt ids, or channel-specific fields. Provider details remain
nested under metadata rather than expanding the core contract into a
channel matrix.

## Receipts

Channel adapter contracts require `craik.capability_receipt`
receipts. Receipt capabilities must be declared by the adapter
contract, so inbound and outbound channel activity stays auditable
under the same policy model as runner and tool actions.

## Local store

The v0.8.0 gateway artifacts are durable store contracts. The local
store exposes typed helpers for channel adapter contracts, identity
pairings, allowlists, channel policy envelopes, gateway schedules,
scheduled automations, and gateway receipts so an accepted ingress or
scheduling decision can be inspected after restart.

## Trust boundaries

<div className="craik-grid">

<div><h4>Policy envelopes required</h4></div>
<div><h4>Allowlist enforcement</h4></div>
<div><h4>Inbound identity handling</h4></div>
<div><h4>Secrets outside contract &amp; config</h4></div>

</div>

Future channel adapters can add delivery-specific behavior, but they
must keep authorization, identity pairing, redaction, and receipt
emission visible at this contract boundary.

## What's next

<div className="craik-next">

<a href="../messaging-channel-adapter/">
<strong>Reference</strong>
<span>Messaging channel adapter</span>
<small>The first concrete fixture.</small>
</a>

<a href="../channel-identity-pairing/">
<strong>Reference</strong>
<span>Channel identity pairing</span>
<small>Paired, unpaired, and revoked sender authority states.</small>
</a>

<a href="../channel-allowlists/">
<strong>Reference</strong>
<span>Channel allowlists</span>
<small>Deny-by-default ingress filtering.</small>
</a>

</div>
