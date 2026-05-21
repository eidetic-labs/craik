# Reference integrations

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

`craik.reference_integration` — safe, reproducible examples for
skills, plugins, and adapters that show known-good paths through the
ecosystem.

</div>

<div className="craik-keypoint">

**Examples, not trust grants.**

Reference integrations must be safe to run locally and reproducible.
They are validation fixtures, not durable trust grants.

</div>

## What it records

<div className="craik-grid">

<div><h4>Integration kind</h4><p><code>skill</code> · <code>plugin</code> · <code>adapter</code>.</p></div>
<div><h4>Matching package or descriptor id</h4></div>
<div><h4>Docs and fixture paths</h4></div>
<div><h4>Check commands</h4></div>
<div><h4>Receipt links</h4><p>When relevant.</p></div>
<div><h4>Compatibility notes</h4></div>
<div><h4>Provenance</h4></div>

</div>

## Scope

<div className="craik-decision">

<div>
<h4>Skill reference</h4>
<p>Package with instructions and expected contracts.</p>
</div>

<div>
<h4>Plugin reference</h4>
<p>Descriptor plus receipts and checks.</p>
</div>

<div>
<h4>Adapter reference</h4>
<p>Adapter package with compatibility and runner metadata links.</p>
</div>

</div>

Each reference kind links only the matching contract family. Skill
references link a skill package, plugin references link a plugin
descriptor and at least one receipt, and adapter references link an
adapter package. Mixed links are rejected so examples stay narrow and
reviewable.

<div className="craik-keypoint">

**Reproducible offline.**

Each reference must include enough docs, fixtures, and checks for
another agent to rerun it without relying on private state.

</div>

## What's next

<div className="craik-next">

<a href="../../guides/community-skills/">
<strong>Guide</strong>
<span>Community skills</span>
<small>How skill references compose with community distribution.</small>
</a>

<a href="../../guides/community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>How plugin references compose with community plugin review.</small>
</a>

<a href="../adapter-packages/">
<strong>Reference</strong>
<span>Adapter packages</span>
<small>The adapter distribution metadata an adapter reference links to.</small>
</a>

</div>
