# Plugin descriptors

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.plugin_descriptor` contract — governed plugin metadata
that declares needs without granting runtime authority.

</div>

<div className="craik-keypoint">

**Declarations, not authorizations.**

Descriptors do not authorize execution, file writes, network access,
memory access, or GitHub operations. Runtime authority remains in
`craik.capability_grant` and must be checked before a runner invokes
plugin behavior.

</div>

## What it records

<div className="craik-grid">

<div><h4>Identity</h4><p><code>id</code> · <code>name</code> · <code>publisher</code> · <code>plugin_version</code>.</p></div>
<div><h4>Trust boundary</h4><p>Where the descriptor is valid: project, repository, organization, user, or external.</p></div>
<div><h4>Entrypoints</h4><p>Command · module · workflow · service · docs paths exposed by the plugin.</p></div>
<div><h4>Capability declarations</h4><p>Requested capabilities · operations · targets · risk · whether an explicit grant is required.</p></div>
<div><h4>Docs and security notes</h4><p>Required for review.</p></div>
<div><h4>Compatibility metadata</h4><p>Craik versions · Python versions · platforms · support status.</p></div>
<div><h4>Optional links</h4><p>To skill packages and provenance records.</p></div>

</div>

## Validation

Craik **rejects** descriptors that:

<div className="craik-grid">

<div><h4>Omit required fields</h4><p>Entrypoints · capabilities · docs · security notes · compatibility metadata.</p></div>
<div><h4>Use a non-version-like <code>plugin_version</code></h4></div>
<div><h4>Use non-version-like Craik compatibility entries</h4><p>Compatibility uses semantic-version-like Craik versions.</p></div>
<div><h4>Set <code>runtime_authority</code> to <code>true</code></h4></div>
<div><h4>Declare high or critical risk capabilities</h4><p>Without requiring explicit grants.</p></div>
<div><h4>Request grants without boundaries</h4><p>Grant-required capabilities must name operations and targets.</p></div>

</div>

This keeps plugin discovery and review independent from policy
decisions about what the current run is allowed to do.

Supported descriptors must also declare Python versions and platforms.
Unsupported descriptors must include notes explaining the boundary so
operators know whether the plugin is intentionally unavailable or just
underspecified.

## What's next

<div className="craik-next">

<a href="../plugin-capability-grants/">
<strong>Reference</strong>
<span>Plugin capability grants</span>
<small>The grant contract that authorizes bounded actions.</small>
</a>

<a href="../plugin-probation/">
<strong>Reference</strong>
<span>Plugin probation</span>
<small>How new descriptors enter trusted use.</small>
</a>

<a href="../../guides/community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>Review boundaries for plugin authors.</small>
</a>

</div>
