# Post-MVP scope

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The surfaces intentionally outside Craik's first robust MVP. Each
section names a surface, what ships pre-MVP, and what crosses into
post-MVP territory. Use this when triaging scope creep.

</div>

<div className="craik-keypoint">

**`0.x.0` is not a `1.0.0` promise.**

MVP scope is limited to the accepted documentation reconciliation
workflow, deterministic OpenAI and Anthropic provider paths, local
state, policy-gated side effects, memory proposals, receipts,
handoffs, work graphs, package release workflows, and Docusaurus
documentation.

</div>

## Gateway Daemon

v0.8.0 ships a foreground local gateway daemon with `/health`,
pid-file locking, persisted runtime state, webhook validation, channel
contracts, scheduled automation helpers, and gateway receipts.
Post-MVP gateway work is the broader production service: hosted/public
deployment, TLS termination, always-on scheduler supervision, broad
third-party adapters, inbound messaging loops, webhook dispatchers, and
production dispatch orchestration. Those surfaces must not be
documented as operational support until they have policy checks,
receipts, supervision, security review, and CI coverage.

## Operator UI

Formatter contracts and read-only operator view helpers can support
local inspection. A complete TUI, web dashboard, mutation-capable
console, and hosted operator service are post-MVP.

## Additional Live Runners

OpenAI and Anthropic are the MVP provider targets. Fixture and
prompt-handoff adapters can remain documented for local testing and
preview workflows, but additional live runner adapters are post-MVP
until they meet the same certification, budget, retry, redaction,
receipt, and side-effect boundaries.

## Companion And Visual Surfaces

Desktop companion, mobile companion, voice, browser, visual workspace,
multimodal, and adjacent runtime surfaces are posture and contract
work before MVP. Product applications, always-on actions, remote
action queues, credential storage, and direct mutation through those
surfaces are post-MVP.

## Marketplace And Community Ecosystem

Community skill, plugin, marketplace, index, probation, and reference
integration docs describe future contribution mechanics. They do not
imply a supported public marketplace, automatic trust, or runtime
authority in the MVP.

## Documentation posture

Every doc that covers a deferred surface uses one of three postures.

<div className="craik-fields">

<div>
<dt>Posture</dt>
<dt><span className="craik-fields__type">Required evidence</span></dt>
<dd>Meaning</dd>
</div>

<div>
<dt><code>implemented</code></dt>
<dt><span className="craik-fields__type">tests + CI</span></dt>
<dd>Available in the MVP path with tests and CI coverage.</dd>
</div>

<div>
<dt><code>preview</code></dt>
<dt><span className="craik-fields__type">contract / fixture</span></dt>
<dd>Contract, helper, fixture, or deterministic local workflow only.</dd>
</div>

<div>
<dt><code>post-MVP</code></dt>
<dt><span className="craik-fields__type">deferred</span></dt>
<dd>Intentionally outside the first robust MVP.</dd>
</div>

</div>

<div className="craik-keypoint">

**Don't describe deferred surfaces as operational.**

Unless the same page names the proof workflow, required policy
boundary, receipts, and validation command, a deferred surface must
not be described as operational.

</div>

## What's next

<div className="craik-next">

<a href="../../limitations/">
<strong>Read</strong>
<span>Limitations</span>
<small>The honest current-vs-deferred boundary for v0.1.</small>
</a>

<a href="../../mvp-roadmap/">
<strong>Read</strong>
<span>MVP roadmap</span>
<small>The checklist that turns these gates into release-quality workflows.</small>
</a>

<a href="../../roadmap/">
<strong>Read</strong>
<span>Roadmap</span>
<small>The release-gate sequence through v0.12.</small>
</a>

</div>
