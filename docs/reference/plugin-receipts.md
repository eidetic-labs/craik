# Plugin receipts

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.plugin_receipt` contract — what plugin actions and outputs
record, common outcomes, and how the receipt keeps descriptor
identity separate from runtime authority.

</div>

<div className="craik-keypoint">

**Grants explain why; receipts explain what.**

Capability grants show why an action was allowed. The receipt records
what happened. Both must be redacted.

</div>

Runtime writers should create plugin receipts through Craik's receipt
factory rather than constructing writable receipts directly. The factory
redacts result summaries and metadata before persistence, and local
stores attach an integrity HMAC that is verified whenever plugin receipts
are read back.

## Linked records

`craik.plugin_receipt` links a plugin action to:

<div className="craik-grid">

<div><h4>Task and actor</h4></div>
<div><h4>Plugin descriptor</h4><p>And optional probation record.</p></div>
<div><h4>Capability grants</h4></div>
<div><h4>Trust boundary</h4></div>
<div><h4>Redacted result summary</h4></div>
<div><h4>Evidence and handoff records</h4></div>

</div>

## Outcomes

<div className="craik-fields">

<div>
<dt>Outcome</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Meaning</dd>
</div>

<div>
<dt><code>passed</code></dt>
<dt><span className="craik-fields__type">success</span></dt>
<dd>The plugin action completed successfully.</dd>
</div>

<div>
<dt><code>failed</code></dt>
<dt><span className="craik-fields__type">error</span></dt>
<dd>The plugin action ran but did not complete successfully.</dd>
</div>

<div>
<dt><code>denied</code></dt>
<dt><span className="craik-fields__type">blocked</span></dt>
<dd>Policy or missing authority blocked the action.</dd>
</div>

</div>

<div className="craik-keypoint">

**Every outcome links evidence and handoff.**

Successful, failed, and denied plugin receipts all require evidence
and handoff links so reviewers can reconstruct the action boundary
without reading raw plugin output.

The optional probation link is shown in the operator receipt view when
present. Receipts may omit the probation id for already-promoted
plugins, but an empty probation id is rejected. Result metadata must
not contradict the receipt redaction flag.

</div>

## What's next

<div className="craik-next">

<a href="../plugin-descriptors/">
<strong>Reference</strong>
<span>Plugin descriptors</span>
<small>What plugins declare before running.</small>
</a>

<a href="../plugin-capability-grants/">
<strong>Reference</strong>
<span>Plugin capability grants</span>
<small>The authority side of the descriptor / grant / receipt triangle.</small>
</a>

<a href="../../guides/community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>Author and review expectations.</small>
</a>

</div>
