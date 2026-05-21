# Community skills

<p className="craik-meta"><span>3 min read</span><span>For maintainers &amp; integrators</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

Safe package shape and review expectations for community skills.
Skills package reusable instructions, examples, and optional assets
for a bounded workflow — they must be easy to inspect before use and
safe to run under Craik policy.

</div>

<div className="craik-keypoint">

**Post-MVP scope.**

Broad community distribution and marketplace workflows are post-MVP scope.
This guide describes safe package shape and review expectations — it
does not imply a supported public marketplace or automatic trust.
See [Post-MVP Scope](../reference/post-mvp-scope.md).

</div>

## Authoring

A community skill should include:

<div className="craik-grid">

<div><h4>Clear <code>SKILL.md</code> entrypoint</h4></div>
<div><h4>Versioned skill package record</h4></div>
<div><h4>Input / output schemas</h4></div>
<div><h4>Context requirements</h4><p>Required inputs, trust boundary, and missing-context behavior.</p></div>
<div><h4>Docs</h4><p>Intended use and limitations.</p></div>
<div><h4>Provenance</h4><p>For copied, generated, or externally sourced material.</p></div>
<div><h4>Examples or fixtures</h4><p>That can be validated locally.</p></div>

</div>

Use [`craik.skill_package`](../reference/skill-packages.md) for
package metadata. Use
[`craik.skill_registry`](../reference/skill-registries.md) to record
whether a skill is project-local or global and how precedence is
resolved.

Each expected input schema needs a matching context requirement. The
requirement records whether the input is required, which trust boundary
is acceptable, and whether missing context should reject the run, be
recorded as an omission, or allow a degraded run. This prevents
community skills from depending on implicit agent state.

## Scoping

<div className="craik-decision">

<div>
<h4>Project-local skills</h4>
<p>Live with the project · use a project trust boundary · take precedence over global skills with the same package.</p>
</div>

<div>
<h4>Global skills</h4>
<p>Treated as user-supplied defaults.</p>
</div>

</div>

Registries must list every active entry in `active_entry_ids`, and
`precedence_order` must include only active entries. Project-scoped
entries outrank global entries for the same package, so a repository
can override a global default without silently inheriting it.

Skill invocation context is per-run state. Use
[`craik.skill_invocation_context`](../reference/skill-contexts.md)
to record inputs, outputs, omissions, policy links, receipts, and
evidence for one invocation.

## Review

Review community skills before adopting them:

<ol className="craik-steps">
<li>Confirm the package version and entrypoints.</li>
<li>Inspect docs and examples.</li>
<li>Verify expected input and output schemas.</li>
<li>Verify context requirements cover every expected input schema.</li>
<li>Check provenance links.</li>
<li>Confirm registry scope and precedence match the project boundary.</li>
<li>Confirm the skill does not claim runtime authority.</li>
<li>Run local checks for linked fixtures or examples.</li>
</ol>

Reference integrations can document known-good skill examples. See
[`craik.reference_integration`](../reference/reference-integrations.md)
for the fixture and check structure.

## Security boundaries

<div className="craik-keypoint">

**Skills are instructions, not authority.**

They do not grant shell, network, repository, memory, or GitHub
authority. Runtime authority comes from policy and capability grants.
Treat unreviewed community skills as untrusted input until provenance,
docs, and expected outputs have been checked.

</div>

Do not place secrets in skill docs, fixtures, examples, or assets.
Persisted skill invocation context must be redacted and
evidence-linked.

## What's next

<div className="craik-next">

<a href="../community-plugins/">
<strong>Guide</strong>
<span>Community plugins</span>
<small>The companion guide for executable extensions.</small>
</a>

<a href="../../reference/skill-packages/">
<strong>Reference</strong>
<span>Skill packages</span>
<small>The package metadata contract.</small>
</a>

<a href="../../reference/skill-contexts/">
<strong>Reference</strong>
<span>Skill invocation contexts</span>
<small>The per-run record produced when a skill executes.</small>
</a>

</div>
