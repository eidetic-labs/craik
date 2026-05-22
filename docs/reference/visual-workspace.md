# Live visual workspace decision

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The `VisualWorkspaceSurface` contract — what it records, the decision
rules, and the current shipped posture.

</div>

<div className="craik-keypoint">

**Read-only over existing work records.**

A visual workspace may make work graph state easier to scan — it must
not become an unreviewed mutation layer.

</div>

## What it records

<div className="craik-grid">

<div><h4>Surface id</h4></div>
<div><h4>Support level</h4><p><code>supported</code> · <code>experimental</code> · <code>deferred</code>.</p></div>
<div><h4>Read-only posture</h4></div>
<div><h4>Work graph link preservation</h4></div>
<div><h4>Evidence link preservation</h4></div>
<div><h4>Receipt requirement</h4></div>
<div><h4>Visual state redaction</h4></div>
<div><h4>Accessibility controls</h4></div>
<div><h4>Raw canvas payload persistence</h4></div>
<div><h4>Documentation reference</h4></div>

</div>

## Decision rules

<div className="craik-decision">

<div>
<h4>Allowed (supported)</h4>
<ul>
<li>Read-only graph inspection</li>
<li>Visual state redaction</li>
<li>Accessibility controls</li>
<li>Work graph links</li>
<li>Evidence links</li>
<li>Receipts</li>
</ul>
</div>

<div>
<h4>Blocked</h4>
<ul>
<li>Persists raw canvas payloads</li>
<li>Mutates workflow state</li>
<li>Skips visual state redaction</li>
<li>Omits accessibility controls</li>
<li>Loses work graph or evidence links</li>
<li>Skips receipts</li>
</ul>
</div>

</div>

## Current posture

<div className="craik-keypoint">

**Read-only views first.**

Read-only visual work-graph views can be supported when they satisfy
the controls above. Live mutating canvases, raw visual state
persistence, and canvas-driven workflow mutation are deferred until a
later bridge defines explicit policy, evidence, receipt, and
accessibility behavior.

</div>

## What's next

<div className="craik-next">

<a href="../work-graph-visual-bridge/">
<strong>Reference</strong>
<span>Work graph visual bridge</span>
<small>The bridge that projects work-graph state into a renderable record.</small>
</a>

<a href="../accessibility-requirements/">
<strong>Reference</strong>
<span>Accessibility requirements</span>
<small>The accessibility floor visual surfaces respect.</small>
</a>

<a href="../../guides/companion-app-security/">
<strong>Guide</strong>
<span>Companion app security</span>
<small>The author-facing security posture for visual surfaces.</small>
</a>

</div>
