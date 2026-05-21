# Adapter packages

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.adapter_package` contract — runner adapter distribution
metadata that describes how an adapter loads and what surfaces it
exposes.

</div>

<div className="craik-keypoint">

**Distribution metadata, not authority.**

Adapter packages do not grant runtime authority. Policy envelopes and
capability grants still decide what a run may do.

</div>

## What it records

<div className="craik-grid">

<div><h4>Adapter identity &amp; package version</h4></div>
<div><h4>Adapter implementation entrypoints</h4></div>
<div><h4>Capability surfaces</h4><p>Exposed by the adapter.</p></div>
<div><h4>Compatibility</h4><p>Craik · runner mode · Python · platform.</p></div>
<div><h4>Linked runner metadata &amp; plugin descriptors</h4></div>
<div><h4>Docs · provenance · version constraints</h4></div>

</div>

## Expectations

<ol className="craik-steps">
<li>At least one entrypoint.</li>
<li>At least one capability surface.</li>
<li>Docs and provenance.</li>
<li>Version-like package version.</li>
<li>Semantic-version-like package and Craik compatibility versions.</li>
<li>Compatibility names at least one supported runner mode, Python version, and platform.</li>
</ol>

Compatibility is an execution boundary, not a suggestion. Adapter
packages must declare the Craik versions they support as
`MAJOR.MINOR.PATCH` values, plus the runner modes, Python versions,
and platforms used for validation.

## What's next

<div className="craik-next">

<a href="../runner-adapter-contract/">
<strong>Reference</strong>
<span>Runner adapter contract</span>
<small>The contract every packaged adapter implements.</small>
</a>

<a href="../runner-metadata/">
<strong>Reference</strong>
<span>Runner metadata</span>
<small>The identity snapshot adapter packages link to.</small>
</a>

<a href="../../guides/community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>Author and review expectations for distributed adapters.</small>
</a>

</div>
