# Plugin probation

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.plugin_probation` contract — how new or changed plugins
stay out of durable trust until review criteria are satisfied.

</div>

<div className="craik-keypoint">

**Probation starts at the default.**

Records start with <code>status: probationary</code> and
<code>durable_trust_granted: false</code>. Probationary records cannot
include a decision or grant durable trust.

</div>

## What it links

<div className="craik-grid">

<div><h4>Plugin descriptor</h4></div>
<div><h4>Policy envelope</h4></div>
<div><h4>Review criteria</h4></div>
<div><h4>Compatibility checks</h4></div>
<div><h4>Evidence and receipt records</h4></div>
<div><h4>Promotion / rejection / expiration decisions</h4></div>
<div><h4>Whether durable trust was granted</h4></div>

</div>

## Review states

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Required</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>promoted</code></dt>
<dt><span className="craik-fields__type">promote decision</span></dt>
<dd>Plus passing required criteria, criterion evidence, and compatibility checks. Promotion does not have to grant durable trust — the field defaults to false so callers make durable trust explicit.</dd>
</div>

<div>
<dt><code>rejected</code></dt>
<dt><span className="craik-fields__type">reject decision</span></dt>
<dd>Records the explicit decision.</dd>
</div>

<div>
<dt><code>expired</code></dt>
<dt><span className="craik-fields__type">expire decision</span></dt>
<dd>Plus <code>expires_at</code>.</dd>
</div>

</div>

<div className="craik-keypoint">

**Auditable without mixing.**

These states make plugin review auditable without mixing descriptor
metadata with runtime authority or policy grants.

</div>

Decisions require evidence links. Criteria marked as passed also
require evidence links, so a plugin cannot become promoted based only
on an unchecked status change.

## What's next

<div className="craik-next">

<a href="../plugin-descriptors/">
<strong>Reference</strong>
<span>Plugin descriptors</span>
<small>What the descriptor declares before review.</small>
</a>

<a href="../plugin-capability-grants/">
<strong>Reference</strong>
<span>Plugin capability grants</span>
<small>The grants a promoted plugin can earn.</small>
</a>

<a href="../../guides/community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>Review boundaries for plugin authors.</small>
</a>

</div>
