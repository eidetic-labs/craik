# Community plugins

<p className="craik-meta"><span>3 min read</span><span>For maintainers &amp; integrators</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

Safe metadata and review boundaries for community plugins —
descriptors, probation, capabilities, receipts, reference integrations,
and security boundaries. Treat all community plugins as untrusted
until descriptor, provenance, review state, grants, and receipts have
been inspected.

</div>

<div className="craik-keypoint">

**Post-MVP scope.**

Broad plugin marketplace and community ecosystem workflows are post-MVP scope.
This guide describes safe metadata and review boundaries — it does
not imply a supported public marketplace or runtime authority. See
[Post-MVP Scope](../reference/post-mvp-scope.md).

</div>

## Authoring

A community plugin should include:

<div className="craik-grid">

<div><h4>Governed plugin descriptor</h4></div>
<div><h4>Versioned entrypoints</h4></div>
<div><h4>Declared capability needs</h4></div>
<div><h4>Compatibility metadata</h4></div>
<div><h4>Docs and security notes</h4></div>
<div><h4>Provenance</h4><p>For copied, generated, or external material.</p></div>
<div><h4>Examples or fixtures</h4><p>That can be checked locally.</p></div>

</div>

Use [`craik.plugin_descriptor`](../reference/plugin-descriptors.md)
for plugin identity, entrypoints, declared capabilities, docs,
security metadata, and compatibility. **Descriptors declare needs;
they do not grant runtime authority.**

Descriptors must declare a trust boundary and semantic-version-like
plugin and Craik compatibility versions. Grant-required capabilities
must name concrete operations and targets so review can compare the
descriptor request to the eventual grant.

## Review and probation

New or changed community plugins should start in probation. Use
[`craik.plugin_probation`](../reference/plugin-probation.md) to
record review criteria, compatibility checks, evidence, receipts, and
promotion / rejection / expiration decisions.

<div className="craik-keypoint">

**Preserve denials.**

Promotion requires passing required criteria and compatibility checks.
Rejected and expired plugins must preserve the decision rationale so
later agents don't repeat the same review.
Decisions require evidence, and criteria marked as passed require
evidence links before a plugin can be promoted.

</div>

## Capabilities

Plugin capability grants must be explicit and least-privilege. Use
[`craik.plugin_capability_grant`](../reference/plugin-capability-grants.md)
to scope authority to a plugin descriptor, target paths, operations,
approval requirements, and expiry.

<div className="craik-keypoint">

**Authority comes from grants, not descriptors.**

Do not infer authority from descriptor metadata, package names, docs,
or prior successful runs. Capability grants and policy envelopes
decide what a plugin may do in the current run.
Grants must name explicit operations and scoped targets. Denied,
expired, and approval-required grants must not be treated as ambient
authority; runtime callers should check the current operation and
expiry before execution.

</div>

## Receipts

Every meaningful plugin action leaves a redacted receipt. Use
[`craik.plugin_receipt`](../reference/plugin-receipts.md) to link
plugin actions to descriptors, capability grants, evidence, handoffs,
trust boundaries, and results.

Receipts summarize passed, failed, and denied actions without storing
raw secrets or unredacted plugin output.
Receipt result metadata must not contradict the receipt redaction
flag, and probation links should be preserved while a plugin is under
review.

## Adapters

Adapter packages are distribution metadata for runner integrations,
not authority grants. Use
[`craik.adapter_package`](../reference/adapter-packages.md) to record
adapter entrypoints, capability surfaces, supported runner modes,
Python versions, platforms, linked plugin descriptors, docs, and
provenance. Adapter compatibility should be treated as a hard
execution boundary.

## Reference paths

Use [`craik.reference_integration`](../reference/reference-integrations.md)
to publish safe, reproducible examples that link docs, fixtures,
checks, receipts, and compatibility notes. **Reference integrations
are examples, not trust grants.**

## Security boundaries

<div className="craik-fields">

<div>
<dt>Surface</dt>
<dt><span className="craik-fields__type">Role</span></dt>
<dd>What it does</dd>
</div>

<div>
<dt>Descriptors</dt>
<dt><span className="craik-fields__type">metadata</span></dt>
<dd>Declare metadata only — no authority.</dd>
</div>

<div>
<dt>Probation</dt>
<dt><span className="craik-fields__type">review trust</span></dt>
<dd>Records review trust.</dd>
</div>

<div>
<dt>Capability grants</dt>
<dt><span className="craik-fields__type">authorize</span></dt>
<dd>Authorize bounded actions.</dd>
</div>

<div>
<dt>Receipts</dt>
<dt><span className="craik-fields__type">evidence</span></dt>
<dd>Record what happened.</dd>
</div>

<div>
<dt>Policy envelopes</dt>
<dt><span className="craik-fields__type">runtime authority</span></dt>
<dd>Remain the source of runtime authority.</dd>
</div>

<div>
<dt>Adapter packages</dt>
<dt><span className="craik-fields__type">distribution</span></dt>
<dd>Describe runner integration surfaces without granting authority.</dd>
</div>

</div>

<div className="craik-keypoint">

**No secrets in any plugin artifact.**

Do not include secrets in plugin docs, fixtures, descriptors,
receipts, or examples. Persist only redacted outputs and
evidence-linked summaries.

</div>

## What's next

<div className="craik-next">

<a href="../community-skills/">
<strong>Guide</strong>
<span>Community skills</span>
<small>The companion guide for instruction-only packages.</small>
</a>

<a href="../../reference/plugin-descriptors/">
<strong>Reference</strong>
<span>Plugin descriptors</span>
<small>The shipped descriptor contract.</small>
</a>

<a href="../capability-grants/">
<strong>Guide</strong>
<span>Capability grants</span>
<small>How the runtime turns descriptors into bounded authority.</small>
</a>

</div>
