# Skill packages

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.skill_package` contract — reusable instructions,
entrypoints, docs, and assets. Packages don't carry plugin runtime
authority.

</div>

<div className="craik-keypoint">

**No runtime authority on packages.**

Runtime authority is always <code>false</code>. Any executable
authority must be represented through the separate plugin governance
and grant model.

</div>

## What it records

<div className="craik-grid">

<div><h4>Package id · name · version · description</h4></div>
<div><h4>One or more entrypoints</h4></div>
<div><h4>Expected input &amp; output schemas</h4></div>
<div><h4>Documentation files</h4></div>
<div><h4>Asset paths</h4></div>
<div><h4>Provenance links</h4></div>
<div><h4>Optional plugin descriptor link</h4></div>

</div>

<div className="craik-keypoint">

**Docs and at least one entrypoint are required.**

</div>

## Versioning

`package_version` must be semantic-version-like: `MAJOR.MINOR.PATCH`
with an optional prerelease or build suffix, such as `1.2.3-beta.1`
or `1.2.3+build.7`. Partial versions like `1.2` are rejected so
operators can compare package revisions deterministically.

## Required Boundaries

Skill packages describe reusable instructions and examples. Scope is
recorded by `craik.skill_registry`, invocation context is recorded by
`craik.skill_invocation_context`, and executable authority remains in
the plugin governance model. A package that needs runtime side effects
links to a plugin descriptor instead of carrying authority itself.

## What's next

<div className="craik-next">

<a href="../skill-registries/">
<strong>Reference</strong>
<span>Skill registries</span>
<small>How packages enter project-local and global discovery.</small>
</a>

<a href="../skill-contexts/">
<strong>Reference</strong>
<span>Skill invocation contexts</span>
<small>The per-run record produced when a skill executes.</small>
</a>

<a href="../../guides/community-skills/">
<strong>Guide</strong>
<span>Community skills</span>
<small>Author and review expectations.</small>
</a>

</div>
