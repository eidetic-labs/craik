# Skill invocation contexts

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The auditable boundary for one skill run — what was handed in, what
came back, and what was intentionally or accidentally left out.

</div>

<div className="craik-keypoint">

**Context ≠ package.**

The package describes reusable entrypoints and docs. The invocation
context describes what one task actually handed to the skill, what
came back, and what was omitted.

</div>

## What it records

The `craik.skill_invocation_context` contract records:

<div className="craik-grid">

<div><h4>Task · skill package · policy envelope · optional handoff</h4></div>
<div><h4>Input contracts</h4><p>Supplied to the skill, with trust boundary metadata.</p></div>
<div><h4>Output contracts</h4><p>Expected or produced.</p></div>
<div><h4>Omitted context</h4><p>Reason · impact · severity · mitigation.</p></div>
<div><h4>Evidence and receipt links</h4></div>
<div><h4>Redaction status</h4><p>For persisted context.</p></div>

</div>

## Boundaries

<div className="craik-keypoint">

**Policy-linked, redacted, or rejected.**

Craik rejects records without inputs, records with neither outputs nor
omissions, and records that claim unredacted persisted context.

</div>

Missing required outputs are represented as omissions. This makes
failed or partial skill runs reviewable instead of silently treating
absent context as irrelevant.

## Package requirements

`craik.skill_package` declares `context_requirements` for each expected
input schema. Each requirement names the schema, whether the input is
required, the trust boundary where it is acceptable, and the
missing-context behavior:

<div className="craik-grid">

<div><h4><code>reject</code></h4><p>Do not invoke the skill without that context.</p></div>
<div><h4><code>record_omission</code></h4><p>Allow the run only when the missing input is recorded as an omission.</p></div>
<div><h4><code>degrade</code></h4><p>Allow a partial run while keeping the missing input visible to reviewers.</p></div>

</div>

Runtime callers can validate a `SkillInvocationContext` against its
`SkillPackage` before execution. That check rejects package mismatches,
missing required inputs, and missing omission records for requirements
that explicitly demand them.

## What's next

<div className="craik-next">

<a href="../skill-telemetry/">
<strong>Reference</strong>
<span>Skill telemetry</span>
<small>Invocation outcomes, durations, validation signals.</small>
</a>

<a href="../skill-packages/">
<strong>Reference</strong>
<span>Skill packages</span>
<small>The reusable package contract this context invokes.</small>
</a>

<a href="../../guides/community-skills/">
<strong>Guide</strong>
<span>Community skills</span>
<small>Author expectations.</small>
</a>

</div>
