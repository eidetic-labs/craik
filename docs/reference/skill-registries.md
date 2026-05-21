# Skill registries

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.skill_registry` contract that records which reusable
skills are available to a project — project-local versus global,
precedence, and provenance.

</div>

<div className="craik-keypoint">

**Project-local wins.**

When a project-local and global entry reference the same skill
package, the project-local entry must outrank the global entry.

</div>

## Entry fields

<div className="craik-grid">

<div><h4><code>skill_package_id</code></h4></div>
<div><h4><code>scope</code></h4><p><code>project</code> or <code>global</code>.</p></div>
<div><h4>Source path</h4></div>
<div><h4>Trust boundary</h4></div>
<div><h4>Numeric precedence</h4></div>
<div><h4>Active state</h4></div>
<div><h4>Provenance links</h4></div>
<div><h4>Declaration owner &amp; timestamp</h4></div>

</div>

<div className="craik-keypoint">

**Scope discipline.**

Project-scoped entries require <code>project_id</code>. Global entries
must omit <code>project_id</code>. This keeps global discovery from
being confused with project-local authority.

</div>

## Precedence

Lower `precedence` values win. **Active precedence values must be
unique.**

The registry can also record `precedence_order` for consumers that
want a stable ordered list of active skill entry ids. Every active
entry must appear in `active_entry_ids`, and `precedence_order` must
not include inactive entries. This keeps project-local overrides and
global defaults auditable without consumers guessing which entries are
currently live.

## Provenance

Every registry entry requires provenance. Discovery should preserve
the source that caused a skill to enter the registry — a project skill
path, a global skill path, or an evidence record captured during
onboarding.

## What's next

<div className="craik-next">

<a href="../skill-packages/">
<strong>Reference</strong>
<span>Skill packages</span>
<small>The package contract entries reference.</small>
</a>

<a href="../skill-contexts/">
<strong>Reference</strong>
<span>Skill invocation contexts</span>
<small>The per-run record produced when a registered skill executes.</small>
</a>

<a href="../../guides/community-skills/">
<strong>Guide</strong>
<span>Community skills</span>
<small>How skills enter the registry.</small>
</a>

</div>
