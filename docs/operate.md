---
id: operate
title: Operate
sidebar_label: Overview
sidebar_position: 0
description: Run, monitor, and maintain Craik. Inspect operator views, manage state, and handle long-running concerns.
slug: /operate
---

# Operate Craik

This section is for the people running Craik in anger — daily diagnostics,
release practice, the operator views that surface what's happening inside a
run, and the supporting subsystems (gateway, channels, companion apps,
multimodal, locale).

## Implementation paths

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">01</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Day-to-day operations</p>
<h3 className="craik-section-banner__title">
The four commands <em>you reach for most often.</em>
</h3>
<p className="craik-section-banner__lede">
Read-only diagnostics, the contributor quality gates, the safe-update
flow, and the release cadence. Start here if you're picking up an
already-running install or preparing to cut a release.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/doctor/">
<div>
<p className="craik-product-feature__num">Diagnostic · 01</p>
<h4 className="craik-product-feature__title">Doctor diagnostics</h4>
<p className="craik-product-feature__summary">
The read-only health check. Inspects local home, SQLite store, memory
backend, every auth profile, gateway config, gateway prerequisites,
and policy state — without contacting Stigmem or writing receipts.
Run it before going live or whenever something feels off.
</p>
<ul className="craik-product-feature__topics">
<li>read-only</li>
<li>auth-profile health</li>
<li>structured statuses</li>
<li>CI-friendly JSON</li>
</ul>
<span className="craik-product-feature__cta">Run doctor</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Read-only</p>
<p className="craik-product-feature__quote-text">
<code>craik doctor</code> inspects existing local state and environment
variables. It does not create <code>CRAIK_HOME</code>, initialize a
database, contact Stigmem, start a gateway, or write receipts.
</p>
<p className="craik-product-feature__quote-attribution">— Doctor diagnostics · §Read-only</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/development/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Quality gates</span>
</div>
<h4 className="craik-adr-card__title">Development checks</h4>
<p className="craik-adr-card__decision">
The four core gates contributors run before opening a PR: pytest,
ruff, mypy, and <code>craik policy test</code>. Same set CI exercises
on every push — green locally usually means green in CI.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/updating/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Safe update</span>
</div>
<h4 className="craik-adr-card__title">Updating Craik</h4>
<p className="craik-adr-card__decision">
<code>craik update</code> prints safe update guidance only — it does
not modify the installed package, rewrite source checkouts, fetch
remote release metadata, or migrate local state. Operator stays in
control of the actual upgrade.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/release-management/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Release</span>
</div>
<h4 className="craik-adr-card__title">Release management</h4>
<p className="craik-adr-card__decision">
The release cadence and gates for the <code>0.x.0</code> MVP series.
Each published release must be installable, documented, and
recoverable — contracts can change between minor releases but never
without docs and tests.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">02</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Local state &amp; migrations</p>
<h3 className="craik-section-banner__title">
Where state lives — <em>and how to move it.</em>
</h3>
<p className="craik-section-banner__lede">
Four docs cover the on-disk layout, the SQLite local store, the
forward-only migration discipline, and the strict secret-handling
policy that applies whenever data crosses runtime boundaries.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/local-store/">
<div>
<p className="craik-product-feature__num">Persistence · 01</p>
<h4 className="craik-product-feature__title">Local store</h4>
<p className="craik-product-feature__summary">
SQLite at <code>$CRAIK_HOME/state/craik.sqlite3</code>. Holds projects,
tasks, intent locks, case files, run state, receipts, handoffs, memory
proposals, contradictions, and work-graph projections. Schema is
versioned; migrations run on <code>LocalStore.initialize()</code>.
</p>
<ul className="craik-product-feature__topics">
<li>SQLite</li>
<li>versioned schema</li>
<li>forward-only</li>
<li>single source of truth</li>
</ul>
<span className="craik-product-feature__cta">Read the store</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Persistence</p>
<p className="craik-product-feature__quote-text">
Craik uses SQLite for local runtime persistence.
</p>
<p className="craik-product-feature__quote-attribution">— Local store · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/local-state/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">On-disk layout</span>
</div>
<h4 className="craik-adr-card__title">Local state layout</h4>
<p className="craik-adr-card__decision">
The full <code>~/.craik/</code> directory map: <code>config/</code>,
<code>secrets/</code>, <code>state/</code>, <code>cache/</code>,
<code>logs/</code>, <code>receipts/</code>, <code>handoffs/</code>,
<code>case-files/</code>, <code>projects/</code>. Override the root
with <code>CRAIK_HOME</code>.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/local-store-migrations/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Migrations</span>
</div>
<h4 className="craik-adr-card__title">Local store migrations</h4>
<p className="craik-adr-card__decision">
Migrations are forward-only and run during
<code>LocalStore.initialize()</code>. Each step is versioned; a
schema-version table tracks what has applied so a re-initialization
is idempotent.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/secret-migration-policy/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Policy</span>
</div>
<h4 className="craik-adr-card__title">Secret migration policy</h4>
<p className="craik-adr-card__decision">
Migration workflows must never copy secret values across runtime
boundaries. Secret-bearing fields are handled through one of four
policy outcomes — <code>redact</code>, <code>strip</code>,
<code>reference</code>, or <code>reject</code> — never copied as-is.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">03</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Operator views</p>
<h3 className="craik-section-banner__title">
Seventeen <em>read-only inspection surfaces.</em>
</h3>
<p className="craik-section-banner__lede">
Every typed runtime record has a matching named view. Work graph,
handoffs, receipts, contradictions, evidence, delegation queues,
budget, quality, run deltas, memory previews, traps, preferences, and
instruction provenance — each surfaces what an operator needs without
mutating state.
</p>
<p className="craik-section-banner__lede">
<strong>Current scope:</strong> Craik ships the typed view contracts
and formatter helpers today. A complete TUI or dashboard is
<a href="../reference/post-mvp-scope/">post-MVP scope</a>.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/operator-surface/">
<div>
<p className="craik-product-feature__num">Catalog · 01</p>
<h4 className="craik-product-feature__title">Operator surface</h4>
<p className="craik-product-feature__summary">
The umbrella catalog. Names every operator view, the records it reads,
and the formatter helpers Craik ships for rendering them. The contracts
are stable enough today that any TUI or dashboard can be built on top
without renegotiating with core.
</p>
<ul className="craik-product-feature__topics">
<li>view contracts</li>
<li>formatter helpers</li>
<li>read-only</li>
<li>dashboard substrate</li>
</ul>
<span className="craik-product-feature__cta">Read the catalog</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Today</p>
<p className="craik-product-feature__quote-text">
Craik has read-only operator view contracts and formatter helpers. A
complete TUI or dashboard is post-MVP scope.
</p>
<p className="craik-product-feature__quote-attribution">— Operator surface · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/work-graph-explorer/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · graph</span>
</div>
<h4 className="craik-adr-card__title">Work graph explorer</h4>
<p className="craik-adr-card__decision">
Reads <code>craik.work_graph_export</code> and
<code>craik.work_graph_event</code> records. Renders the connected
state of tasks, case files, handoffs, receipts, memory proposals,
evidence, assumptions, and contradictions.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/handoff-viewer/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · handoff</span>
</div>
<h4 className="craik-adr-card__title">Handoff viewer</h4>
<p className="craik-adr-card__decision">
Renders one <code>craik.handoff</code> record with its receipts, memory
proposals, assumptions, context debt, and self-audit. The default
surface for picking up a paused or completed run.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/receipt-viewer/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · receipt</span>
</div>
<h4 className="craik-adr-card__title">Receipt viewer</h4>
<p className="craik-adr-card__decision">
Renders one <code>craik.capability_receipt</code> with operator,
credential, capability, target, reason, result, and the policy
envelope that gated it. Joins back to the task and handoff.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/contradiction-inbox-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · contradiction</span>
</div>
<h4 className="craik-adr-card__title">Contradiction inbox view</h4>
<p className="craik-adr-card__decision">
Read-only view over <code>craik.contradiction_report</code> records.
Surfaces open contradictions with their evidence, owner, proposed
resolution, status, and optional Stigmem conflict id.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/evidence-assumption-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · evidence</span>
</div>
<h4 className="craik-adr-card__title">Evidence &amp; assumption view</h4>
<p className="craik-adr-card__decision">
Renders <code>craik.evidence_reference</code> and
<code>craik.assumption</code> records side by side so a reviewer can
tell what was cited from what was guessed.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/delegation-queue-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · delegation</span>
</div>
<h4 className="craik-adr-card__title">Delegation queue view</h4>
<p className="craik-adr-card__decision">
Read-only view over <code>craik.human_delegation_point</code> records
— the things a run paused on, waiting for a human decision.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/budget-quota-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">08</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · budget</span>
</div>
<h4 className="craik-adr-card__title">Budget &amp; quota view</h4>
<p className="craik-adr-card__decision">
Configured limits, observed usage, missing data, exceeded limits, and
operator notes for tokens, time, and credentials.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/quality-gate-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">09</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · quality</span>
</div>
<h4 className="craik-adr-card__title">Quality gate view</h4>
<p className="craik-adr-card__decision">
Handoff quality scores, evidence coverage, runtime critic findings,
and red-team outcomes — every quality signal in one operator panel.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/run-delta-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">10</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · delta</span>
</div>
<h4 className="craik-adr-card__title">Run delta view</h4>
<p className="craik-adr-card__decision">
Continuity-relevant changes since the previous usable handoff or
resume point. The "what's new since I was last here?" surface.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/memory-impact-preview-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">11</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · memory</span>
</div>
<h4 className="craik-adr-card__title">Memory impact preview view</h4>
<p className="craik-adr-card__decision">
Read-only preview of proposed memory writes <em>before</em> promotion
or direct write attempts. Surfaces facts that would be added or
invalidated and likely contradictions.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/memory-review-nudges/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">12</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · memory</span>
</div>
<h4 className="craik-adr-card__title">Memory review nudges</h4>
<p className="craik-adr-card__decision">
Identifies facts that should be reviewed without directly rewriting
memory. Nudges are signals for the reviewer, never autonomous edits.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/known-traps-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">13</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · traps</span>
</div>
<h4 className="craik-adr-card__title">Known traps view</h4>
<p className="craik-adr-card__decision">
Surfaces known traps and negative knowledge — what <em>not</em> to do
on this project, with reasons. The institutional memory of failed
approaches.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/preference-facts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">14</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · preferences</span>
</div>
<h4 className="craik-adr-card__title">Preference facts</h4>
<p className="craik-adr-card__decision">
Models user and team preferences as reviewable records. Preferences
are facts with explicit scope, not implicit settings buried in config.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/instruction-distillation-view/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">15</span>
<span className="craik-adr-card__status craik-adr-card__status--type">View · instructions</span>
</div>
<h4 className="craik-adr-card__title">Instruction distillation view</h4>
<p className="craik-adr-card__decision">
Renders declared instruction sources, observed source snapshots,
provenance, and distilled proposals so a reviewer can see where each
runtime constraint actually came from.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/instruction-distillation-workflow/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">16</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Workflow · instructions</span>
</div>
<h4 className="craik-adr-card__title">Instruction distillation workflow</h4>
<p className="craik-adr-card__decision">
Turns declared instruction files into reviewed, provenance-linked
runtime constraints. Raw instruction files are evidence — never
authority — until distilled through review.
</p>
<span className="craik-adr-card__cta">Workflow</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/instruction-sources/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">17</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Registry · instructions</span>
</div>
<h4 className="craik-adr-card__title">Instruction sources</h4>
<p className="craik-adr-card__decision">
Registries declaring which project files Craik may use for runtime
instruction distillation. Craik does not treat every Markdown file as
an instruction by default.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">04</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Agents, context &amp; learning</p>
<h3 className="craik-section-banner__title">
How agents onboard, budget context, and <em>feed back into the runtime.</em>
</h3>
<p className="craik-section-banner__lede">
Fifteen docs cover the agent lifecycle: onboarding, context budgeting
and debt, scratchpad rules, exit discipline, knowledge boundaries
(traps, freshness, quality), the learning loop, and the multi-agent
coordination primitives. Every typed object here is reviewable —
nothing rewrites itself silently.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/agent-onboarding/">
<div>
<p className="craik-product-feature__num">Onboarding · 01</p>
<h4 className="craik-product-feature__title">Agent onboarding</h4>
<p className="craik-product-feature__summary">
<code>craik onboard</code> emits the canonical
<code>craik.agent_onboarding</code> payload — project model, policy
envelope, docs boundaries, recent handoffs, unresolved contradictions,
stale-risk warnings, validation commands, Stigmem backend status,
known traps, and allowed next actions.
</p>
<ul className="craik-product-feature__topics">
<li>onboarding payload</li>
<li>policy envelope</li>
<li>continuity context</li>
<li>safe for runners</li>
</ul>
<span className="craik-product-feature__cta">Run onboarding</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Before any work</p>
<p className="craik-product-feature__quote-text">
Use onboarding before starting project work. The command prints a
JSON <code>craik.agent_onboarding</code> report — safe for runners to
parse directly.
</p>
<p className="craik-product-feature__quote-attribution">— Agent onboarding · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/context-budgeting/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guide · context</span>
</div>
<h4 className="craik-adr-card__title">Context budgeting</h4>
<p className="craik-adr-card__decision">
Case files are bounded. The context budget records what was included
and what was omitted — every cut is auditable, every inclusion is
justifiable.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/context-debt/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · context</span>
</div>
<h4 className="craik-adr-card__title">Context debt</h4>
<p className="craik-adr-card__decision">
Records preserve known gaps in the context an agent used. Future
agents decide whether to continue, refresh, or stop — instead of
inheriting silent omissions.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/scratchpad-and-unknowns/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · context</span>
</div>
<h4 className="craik-adr-card__title">Scratchpad &amp; unknowns</h4>
<p className="craik-adr-card__decision">
Scratchpad records are temporary working notes. They must expire and
must not be treated as durable context unless promoted through an
explicit review path.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/exit-discipline/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · context</span>
</div>
<h4 className="craik-adr-card__title">Context requests &amp; exit discipline</h4>
<p className="craik-adr-card__decision">
Structured asks for information needed before work can continue
safely. Link to handoffs, recovery sessions, and unresolved
delegation points so a stop is never silent.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/known-traps/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · knowledge</span>
</div>
<h4 className="craik-adr-card__title">Known traps &amp; negative knowledge</h4>
<p className="craik-adr-card__decision">
Evidence-backed pitfalls agents should avoid, plus statements about
what is <em>not</em> true or <em>not</em> available. Negative
knowledge is first-class, not implied by absence.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/freshness/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · knowledge</span>
</div>
<h4 className="craik-adr-card__title">Tool attestations &amp; freshness</h4>
<p className="craik-adr-card__decision">
Attestations record observed command or tool results with a trust
boundary. Freshness probes track when knowledge should be considered
fresh, expiring, or stale.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/quality-scores/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">08</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · knowledge</span>
</div>
<h4 className="craik-adr-card__title">Quality scores</h4>
<p className="craik-adr-card__decision">
Derived review records. They help agents decide whether a handoff or
evidence set is ready to rely on — but they are not proof of truth
or a substitute for evidence.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/learning-loops/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">09</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guide · learning</span>
</div>
<h4 className="craik-adr-card__title">Learning loops</h4>
<p className="craik-adr-card__decision">
Turn observed skill behavior into reviewable improvement records.
Loops do not let an agent silently rewrite reusable guidance —
proposals route through the skill promotion gates.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/learning-receipts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">10</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · learning</span>
</div>
<h4 className="craik-adr-card__title">Learning receipts</h4>
<p className="craik-adr-card__decision">
Normal <code>craik.capability_receipt</code> records for
self-improvement decisions. Every promotion or rollback is receipted
the same way every other governed action is.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/trajectory-exports/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">11</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · learning</span>
</div>
<h4 className="craik-adr-card__title">Training trajectory exports</h4>
<p className="craik-adr-card__decision">
Stable review and replay format for self-improvement loops. Exports
are deterministic, redacted, and joinable to the runs that produced
the trajectory.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/cross-agent-review/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">12</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · multi-agent</span>
</div>
<h4 className="craik-adr-card__title">Cross-agent review</h4>
<p className="craik-adr-card__decision">
Lets one specialist role request review from another without
collapsing distinct decisions into a single worker result.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/debates/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">13</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · multi-agent</span>
</div>
<h4 className="craik-adr-card__title">Structured debates</h4>
<p className="craik-adr-card__decision">
Captures bounded multi-agent disagreement without erasing minority
positions. Debates are coordination records, not a consensus
mechanism.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/human-delegation/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">14</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · multi-agent</span>
</div>
<h4 className="craik-adr-card__title">Human delegation &amp; scope changes</h4>
<p className="craik-adr-card__decision">
Human delegation points mark places where autonomous agents must stop
or hand off instead of continuing silently. The "ask a human" surface
is itself a typed object.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/runtime-critics/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">15</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · multi-agent</span>
</div>
<h4 className="craik-adr-card__title">Runtime critics &amp; red team</h4>
<p className="craik-adr-card__decision">
Critic and red-team findings are typed review inputs — not facts,
final decisions, or policy overrides — until a separate adjudication
accepts them.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">05</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Gateway &amp; channels</p>
<h3 className="craik-section-banner__title">
Always-on Craik — <em>channels, schedules, webhooks.</em>
</h3>
<p className="craik-section-banner__lede">
Eleven docs cover the gateway surface: the daemon mode, channel
ingress contracts, identity pairing, allowlists, policy envelopes for
externally-driven runs, webhook validation, scheduled task creation,
scheduled automations, and gateway-specific receipts.
</p>
<p className="craik-section-banner__lede">
<strong>Current scope:</strong> gateway daemon mode is a foreground
local service with <code>/health</code>, pid-file locking, persisted
runtime state, webhook validation, and policy-bound channel contracts.
The first messaging adapter is still fixture-only (no Slack / Discord
/ email / SMS yet), and hosted/public dispatch remains post-MVP.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/gateway-daemon/">
<div>
<p className="craik-product-feature__num">Mode · 01</p>
<h4 className="craik-product-feature__title">Gateway daemon mode</h4>
<p className="craik-product-feature__summary">
The always-on entry point — channels, webhooks, schedules, and policy
ingress all hang off this surface. The foreground daemon, health
endpoint, pid-file lock, and persisted lifecycle state ship today;
hosted dispatch and broad third-party adapters remain future work.
</p>
<ul className="craik-product-feature__topics">
<li>foreground daemon</li>
<li>health endpoint</li>
<li>policy ingress</li>
<li>post-MVP hosted dispatch</li>
</ul>
<span className="craik-product-feature__cta">Read gateway mode</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Scope today</p>
<p className="craik-product-feature__quote-text">
Gateway daemon mode is foreground and local-first. The production
dispatch loop and hosted operation remain post-MVP.
</p>
<p className="craik-product-feature__quote-attribution">— Gateway daemon · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/gateway-troubleshooting/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guide</span>
</div>
<h4 className="craik-adr-card__title">Gateway troubleshooting</h4>
<p className="craik-adr-card__decision">
Walks the v0.8 gateway surfaces — setup, diagnostics, channels,
webhooks, schedules, policies, receipts — and the failure modes that
deserve operator attention.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/channel-adapter-contract/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · channel</span>
</div>
<h4 className="craik-adr-card__title">Channel adapter contract</h4>
<p className="craik-adr-card__decision">
<code>craik.channel_adapter_contract</code> defines the boundary for
external operator ingress through always-on gateway channels — the
typed surface every adapter implements against.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/messaging-channel-adapter/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · fixture</span>
</div>
<h4 className="craik-adr-card__title">Messaging channel adapter</h4>
<p className="craik-adr-card__decision">
The first messaging channel adapter is a fixture-only adapter for
controlled gateway ingress. Slack, Discord, email, and SMS adapters
are explicitly out of scope until daemon mode promotes.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/channel-identity-pairing/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · identity</span>
</div>
<h4 className="craik-adr-card__title">Channel identity pairing</h4>
<p className="craik-adr-card__decision">
<code>craik.channel_identity_pairing</code> records the relationship
between an external channel account and a Craik subject — so receipts
can name the human, not just the channel id.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/channel-allowlists/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · ingress</span>
</div>
<h4 className="craik-adr-card__title">Channel allowlists</h4>
<p className="craik-adr-card__decision">
<code>craik.channel_allowlist</code> controls which normalized inbound
channel events may continue past the gateway ingress boundary — the
"who is allowed to ask" surface.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/channel-policy-envelopes/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Policy · ingress</span>
</div>
<h4 className="craik-adr-card__title">Channel policy envelopes</h4>
<p className="craik-adr-card__decision">
Channel ingress uses normal <code>craik.policy_envelope</code> records
— but the selected envelope is intentionally narrower than local
operator authority.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/webhook-ingress/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">08</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · ingress</span>
</div>
<h4 className="craik-adr-card__title">Webhook ingress</h4>
<p className="craik-adr-card__decision">
Validates one request boundary before any gateway dispatch.
Signature, allowlist, payload shape, and identity binding all happen
before the runtime sees the request.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/scheduled-task-creation/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">09</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · schedule</span>
</div>
<h4 className="craik-adr-card__title">Scheduled task creation</h4>
<p className="craik-adr-card__decision">
Cron-like gateway schedules convert one schedule tick into one
deterministic <code>craik.task_request</code>. Same shape that
operator-initiated tasks use.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/scheduled-automations/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">10</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · schedule</span>
</div>
<h4 className="craik-adr-card__title">Scheduled automations</h4>
<p className="craik-adr-card__decision">
Enabled gateway definitions backed by cron-like schedules. Each
evaluation operates on one observed schedule tick at a time so missed
ticks don't pile up into surprise bursts.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/gateway-receipts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">11</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · receipt</span>
</div>
<h4 className="craik-adr-card__title">Gateway receipts</h4>
<p className="craik-adr-card__decision">
Redacted <code>craik.capability_receipt</code> records for always-on
service actions — same shape as task-driven receipts, but tagged
with the channel and ingress path that produced them.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">06</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Companion apps &amp; visual workspaces</p>
<h3 className="craik-section-banner__title">
Governed operator surfaces — <em>not autonomous agents.</em>
</h3>
<p className="craik-section-banner__lede">
Six docs cover the decisions and contracts for desktop and mobile
companions plus live visual workspaces. Every companion is a governed
operator surface over existing work records — it can expose status,
review, and explicit operator-triggered actions, but it cannot widen
runtime authority on its own.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/companion-app-security/">
<div>
<p className="craik-product-feature__num">Security · 01</p>
<h4 className="craik-product-feature__title">Companion app security</h4>
<p className="craik-product-feature__summary">
The umbrella for every companion surface. Companions are read- and
review-oriented; they may surface notifications and explicit operator
actions but never grant runtime authority or sidestep policy. The
security guide is what every desktop / mobile / visual-workspace
adapter must implement against.
</p>
<ul className="craik-product-feature__topics">
<li>read + review</li>
<li>operator-triggered actions</li>
<li>no widening of authority</li>
<li>policy parity</li>
</ul>
<span className="craik-product-feature__cta">Read the security model</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Governed surfaces</p>
<p className="craik-product-feature__quote-text">
Companion app surfaces are governed operator surfaces. They can
expose status, review notifications, and explicit operator-triggered
actions, but they must not [grant runtime authority on their own].
</p>
<p className="craik-product-feature__quote-attribution">— Companion app security · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/desktop-companion/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Decision · desktop</span>
</div>
<h4 className="craik-adr-card__title">Desktop companion</h4>
<p className="craik-adr-card__decision">
The desktop companion decision: status, notifications, and controlled
actions in a tray-style app — bounded by the same governance the CLI
runs under.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/mobile-companion/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Decision · mobile</span>
</div>
<h4 className="craik-adr-card__title">Mobile companion</h4>
<p className="craik-adr-card__decision">
The mobile companion decision: review notifications and
operator-triggered approvals — phone surface focused on review, not
edit.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/visual-workspace/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Decision · visual</span>
</div>
<h4 className="craik-adr-card__title">Live visual workspace</h4>
<p className="craik-adr-card__decision">
Treats visual workspaces and canvases as governed operator surfaces
over existing work records. May make work-graph state easier to read;
must not silently mutate it.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/work-graph-visual-bridge/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Bridge · visual</span>
</div>
<h4 className="craik-adr-card__title">Work graph visual bridge</h4>
<p className="craik-adr-card__decision">
Projects <code>craik.work_graph_export</code> records into portable
visual-workspace records. The contract every visual workspace adapter
implements against.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/accessibility-requirements/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">A11y</span>
</div>
<h4 className="craik-adr-card__title">Accessibility requirements</h4>
<p className="craik-adr-card__decision">
Multimodal and companion surfaces must remain usable without relying
on a single input mode, visual presentation, or motion pattern. A11y
is a contract, not a polish step.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">07</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Multimodal &amp; voice</p>
<h3 className="craik-section-banner__title">
Audio, image, video — <em>under the same governance.</em>
</h3>
<p className="craik-section-banner__lede">
Four docs cover the contracts for non-text artifacts. Multimodal
artifact references travel as typed citations (not embedded media);
voice and speech adapters convert between redacted transcripts and
referenced artifacts while preserving Craik's policy, evidence, and
receipt model.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/multimodal-artifacts/">
<div>
<p className="craik-product-feature__num">Contract · 01</p>
<h4 className="craik-product-feature__title">Multimodal artifact references</h4>
<p className="craik-product-feature__summary">
The typed citation surface for audio, image, video, transcript,
canvas, document, and other media. Workflows cite media by reference,
not by embedded payload — keeps case files, receipts, and handoffs
deterministic and redaction-friendly.
</p>
<ul className="craik-product-feature__topics">
<li>typed citations</li>
<li>no embedded media</li>
<li>redaction-friendly</li>
<li>deterministic</li>
</ul>
<span className="craik-product-feature__cta">Read the contract</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">By reference</p>
<p className="craik-product-feature__quote-text">
Multimodal artifact references let Craik workflows cite audio, image,
video, transcript, canvas, document, and other media without embedding
raw media.
</p>
<p className="craik-product-feature__quote-attribution">— Multimodal artifacts · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/voice-posture/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Posture · voice</span>
</div>
<h4 className="craik-adr-card__title">Voice input &amp; output posture</h4>
<p className="craik-adr-card__decision">
Treats voice input and output as governed operator surfaces — not as
an always-on assistant layer. Voice is opt-in, scoped, and receipted.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/speech-to-text-adapters/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · STT</span>
</div>
<h4 className="craik-adr-card__title">Speech-to-text adapter contract</h4>
<p className="craik-adr-card__decision">
Converts referenced audio artifacts into redacted transcripts while
preserving Craik's policy, evidence, and receipt model. STT is a
boundary, not a passthrough.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/text-to-speech-adapters/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · TTS</span>
</div>
<h4 className="craik-adr-card__title">Text-to-speech adapter contract</h4>
<p className="craik-adr-card__decision">
Converts redacted text requests into referenced generated speech
artifacts while preserving policy, evidence, and receipt model. The
inverse of STT, same boundary discipline.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">08</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Translation &amp; locale</p>
<h3 className="craik-section-banner__title">
Localized docs — <em>without forking the source of truth.</em>
</h3>
<p className="craik-section-banner__lede">
Craik docs start from English source-of-truth pages and use translation
metadata to expose localized versions without changing runtime
identifiers. Two docs cover the strategy and the framework that
implements it.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/translated-docs/">
<div>
<p className="craik-product-feature__num">Strategy · 01</p>
<h4 className="craik-product-feature__title">Translated documentation strategy</h4>
<p className="craik-product-feature__summary">
English pages are the source of truth. Translations live alongside
them via translation metadata, so runtime identifiers, command names,
and schema names stay stable across locales — only operator-facing
prose changes.
</p>
<ul className="craik-product-feature__topics">
<li>English source-of-truth</li>
<li>translation metadata</li>
<li>stable identifiers</li>
<li>locale-aware prose</li>
</ul>
<span className="craik-product-feature__cta">Read the strategy</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Approach</p>
<p className="craik-product-feature__quote-text">
Craik documentation starts from English source-of-truth pages and
uses translation metadata to expose localized docs without changing
runtime identifiers.
</p>
<p className="craik-product-feature__quote-attribution">— Translated docs · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/locale-i18n-framework/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Framework · locale</span>
</div>
<h4 className="craik-adr-card__title">Locale i18n framework</h4>
<p className="craik-adr-card__decision">
Keeps runtime identifiers stable and language-neutral while allowing
docs and operator-facing text to resolve through locale preferences
and translation metadata.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

## Where to go next

- **Build something new** → [Build](build.md)
- **Govern execution** → [Secure](secure.md)
- **Understand the model** → [Learn](learn.md)
