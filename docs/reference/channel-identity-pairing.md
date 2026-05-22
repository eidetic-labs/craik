# Channel identity pairing

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The contract that records the relationship between an external channel
account and a Craik subject — unpaired, paired, revoked states and the
authority each carries.

</div>

<div className="craik-keypoint">

**Pairing maps identity. It does not grant access.**

A messaging adapter can normalize inbound events, but an external
sender cannot authorize privileged ingress until a pairing record
explicitly links that sender to a Craik subject, policy envelope, and
audit trail.

</div>

## States

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Authority</span></dt>
<dd>Required fields</dd>
</div>

<div>
<dt>Unpaired</dt>
<dt><span className="craik-fields__type">observation only</span></dt>
<dd>Channel kind · external account id · expiry timestamp · optional service name · optional display name · optional metadata. <strong>Must not</strong> carry subject, policy envelope, pairing audit, or revocation fields. Does not allow privileged ingress.</dd>
</div>

<div>
<dt>Paired</dt>
<dt><span className="craik-fields__type">conditional</span></dt>
<dd>Craik subject · policy envelope id · pairing timestamp · actor that approved · expiry timestamp · at least one audit id. Authorizes privileged ingress only through the linked policy envelope and only before expiry when later allowlist and capability checks pass.</dd>
</div>

<div>
<dt>Revoked</dt>
<dt><span className="craik-fields__type">never</span></dt>
<dd>Preserves the original subject and pairing audit fields, then adds revocation timestamp · actor that revoked · reason · revocation audit id. <strong>Never</strong> allows privileged ingress.</dd>
</div>

</div>

## Authority limits

<div className="craik-keypoint">

**Identity maps a sender; it doesn't grant access.**

Gateway policy, channel allowlists, capability grants, redaction, and
receipts still decide what can happen after an inbound event is
normalized. Helper-created pairing records default to a 24-hour expiry;
expired pairings cannot authorize privileged ingress.

</div>

## What's next

<div className="craik-next">

<a href="../channel-allowlists/">
<strong>Reference</strong>
<span>Channel allowlists</span>
<small>The selector filter that runs alongside pairing.</small>
</a>

<a href="../channel-policy-envelopes/">
<strong>Reference</strong>
<span>Channel policy envelopes</span>
<small>The policy selected after pairing and allowlist pass.</small>
</a>

<a href="../gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>How pairing decisions persist.</small>
</a>

</div>
