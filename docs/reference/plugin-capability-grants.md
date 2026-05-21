# Plugin capability grants

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.plugin_capability_grant` contract — runtime authority
scoped to one plugin descriptor, with explicit operations, expiry, and
approval state.

</div>

<div className="craik-keypoint">

**Least-privilege only.**

A plugin that only needs read access receives only <code>read</code>,
even if the underlying policy profile could allow broader authority.
Grants must name explicit operations and a scoped target; broad
operations such as <code>*</code> or <code>all</code> are rejected.

</div>

## What it records

<div className="craik-grid">

<div><h4>Task and plugin descriptor</h4></div>
<div><h4>Policy envelope</h4></div>
<div><h4>Capability name</h4></div>
<div><h4>Target paths and exclusions</h4></div>
<div><h4>Allowed operations</h4></div>
<div><h4>Grant status</h4></div>
<div><h4>Approval requirement &amp; approver</h4></div>
<div><h4>Expiry</h4></div>
<div><h4>Evidence and receipt links</h4></div>

</div>

## States

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Required</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>allowed</code></dt>
<dt><span className="craik-fields__type">expiry</span></dt>
<dd>If approval is required, <code>approved_by</code> is also required.</dd>
</div>

<div>
<dt><code>denied</code></dt>
<dt><span className="craik-fields__type">no approver</span></dt>
<dd>Must not include <code>approved_by</code>.</dd>
</div>

<div>
<dt><code>expired</code></dt>
<dt><span className="craik-fields__type"><code>expires_at</code></span></dt>
<dd>Required.</dd>
</div>

<div>
<dt><code>approval_required</code></dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Must set <code>approval_required</code> and must not include <code>approved_by</code> until a human or policy decision approves.</dd>
</div>

</div>

Runtime callers can use `permits_operation(operation, at=...)` to
check whether a grant currently authorizes one operation. The helper
returns `false` for denied, expired, and approval-required grants, for
operations outside the grant, and for allowed grants past their
expiry.

## What's next

<div className="craik-next">

<a href="../plugin-descriptors/">
<strong>Reference</strong>
<span>Plugin descriptors</span>
<small>The descriptor a grant attaches to.</small>
</a>

<a href="../plugin-probation/">
<strong>Reference</strong>
<span>Plugin probation</span>
<small>How new descriptors enter trusted use.</small>
</a>

<a href="../plugin-receipts/">
<strong>Reference</strong>
<span>Plugin receipts</span>
<small>The receipt every plugin action produces.</small>
</a>

</div>
