---
id: learn
title: Learn
sidebar_label: Overview
sidebar_position: 0
description: Understand what Craik is, the runtime mental model, and where the project is going.
slug: /learn
---

# Learn Craik

Craik is a **governed agent-runtime substrate** — the operating layer that turns
coding agents from isolated chat sessions into accountable project workers. This
section explains what that means, the typed objects the runtime is built from,
and how the project intends to grow.

If you'd rather jump straight to installing the CLI, head to
[Build → Getting started](guides/installation.md).

## What's in this section

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">01</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">The product</p>
<h3 className="craik-section-banner__title">
A durable agent runtime — <em>not another framework.</em>
</h3>
<p className="craik-section-banner__lede">
Start here to understand the thesis: agent work needs an
<strong> operating layer</strong> — not more clever prompting — and the
five docs below build that argument from the north star down through
the typed contracts. Every other section of these docs is downstream
of this one.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../vision/">
<div>
<p className="craik-product-feature__num">Featured · 01</p>
<h4 className="craik-product-feature__title">Vision</h4>
<p className="craik-product-feature__summary">
Craik's central claim is that agents need an operating layer that gives
them a shared model of the work, evidence-backed memory, explicit authority
boundaries, structured handoffs, durable artifacts, and a way to resolve
disagreement. Read this first — every other doc is downstream of it.
</p>
<ul className="craik-product-feature__topics">
<li>durable agent runtime</li>
<li>north star</li>
<li>design principles</li>
<li>initial wedge</li>
</ul>
<span className="craik-product-feature__cta">Read the vision</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">North star</p>
<p className="craik-product-feature__quote-text">
A new agent should be able to join a project and understand its current
state better than a human who has been away for two weeks.
</p>
<p className="craik-product-feature__quote-attribution">— Vision · §North Star</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../product-strategy/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="12" cy="18" r="3" />
<circle cx="52" cy="18" r="3" />
<circle cx="32" cy="54" r="3" />
<line x1="12" y1="18" x2="30" y2="32" />
<line x1="52" y1="18" x2="34" y2="32" />
<line x1="32" y1="54" x2="32" y2="34" />
<circle cx="32" cy="32" r="5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · Positioning</p>
<h4 className="craik-product-card__title">Product strategy</h4>
<p className="craik-product-card__summary">
Why Craik is a <em>durable agent runtime</em>, not a framework. The
market wedge, the agent-runner strategy (Codex / Claude / Gemini as
first-class adapters), the MIT license rationale, and the patterns Craik
borrows from local runtimes versus the patterns it adds on top.
</p>
<blockquote className="craik-product-card__quote">
Craik should not be positioned as another agent framework.
<span className="craik-product-card__quote-attr">Product strategy · §Agent Runner Strategy</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>runner strategy</li>
<li>license</li>
<li>gateway ergonomics</li>
<li>multi-agent coordination</li>
</ul>
<p className="craik-product-card__meta">
<span>For: founders &middot; product</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../differentiators/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<line x1="8" y1="32" x2="30" y2="32" />
<line x1="34" y1="32" x2="56" y2="14" />
<line x1="34" y1="32" x2="56" y2="50" stroke-dasharray="3.5 3" />
<circle cx="32" cy="32" r="3" fill="var(--craik-lavender)" stroke="none" />
<circle cx="56" cy="14" r="2.5" />
<circle cx="56" cy="50" r="2.5" stroke-dasharray="2 2" />
</svg>
<p className="craik-product-card__num">03 · What's distinct</p>
<h4 className="craik-product-card__title">Differentiators</h4>
<p className="craik-product-card__summary">
The features that keep the roadmap from collapsing into basic CLI
plumbing. Evidence-first execution, the assumption ledger, the
belief-promotion lifecycle, context budgeting as policy, and end-to-end
run reproducibility.
</p>
<blockquote className="craik-product-card__quote">
No durable assertion without evidence.
<span className="craik-product-card__quote-attr">Differentiators · §Evidence-First Execution</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>evidence-first</li>
<li>assumption ledger</li>
<li>belief promotion</li>
<li>reproducibility</li>
</ul>
<p className="craik-product-card__meta">
<span>For: engineers &middot; reviewers</span>
<span className="craik-product-card__cta">10 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../features/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<line x1="18" y1="14" x2="54" y2="14" />
<line x1="18" y1="22" x2="48" y2="22" />
<line x1="18" y1="30" x2="54" y2="30" />
<line x1="18" y1="38" x2="42" y2="38" />
<line x1="18" y1="46" x2="54" y2="46" />
<line x1="18" y1="54" x2="46" y2="54" />
<circle cx="10" cy="30" r="2.5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">04 · What ships</p>
<h4 className="craik-product-card__title">Features</h4>
<p className="craik-product-card__summary">
The implementable feature surface — every MVP behavior with acceptance
criteria. Project registry, case-file assembler, policy envelope,
capability grants, runner adapters, work graph, receipts, handoffs.
Read this to know exactly what v0.1 ships.
</p>
<blockquote className="craik-product-card__quote">
Read-only tasks default to repo read, memory read, and receipt write.
Implementation tasks require explicit write grants.
<span className="craik-product-card__quote-attr">Features · §Policy Envelope</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>case files</li>
<li>policy envelope</li>
<li>receipts</li>
<li>handoffs</li>
<li>work graph</li>
</ul>
<p className="craik-product-card__meta">
<span>For: implementers</span>
<span className="craik-product-card__cta">10 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../architecture/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="10" y="8" width="44" height="3.5" rx="1" />
<rect x="14" y="16" width="36" height="3.5" rx="1" />
<rect x="10" y="24" width="44" height="3.5" rx="1" />
<rect x="14" y="32" width="36" height="3.5" rx="1" />
<rect x="10" y="40" width="44" height="3.5" rx="1" />
<rect x="14" y="48" width="36" height="3.5" rx="1" />
<rect x="22" y="56" width="20" height="3.5" rx="1" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">05 · How it composes</p>
<h4 className="craik-product-card__title">Architecture</h4>
<p className="craik-product-card__summary">
The seven runtime layers — gateway, project model, orchestration, runner
adapters, capability, memory, work graph, experience — plus the typed
contracts that hold them together. The map for anyone extending Craik
or integrating a new runner.
</p>
<blockquote className="craik-product-card__quote">
The layers should remain separable so Craik can support different model
providers, tool environments, and memory backends without weakening the
product thesis.
<span className="craik-product-card__quote-attr">Architecture · §Layers</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>seven layers</li>
<li>runtime flow</li>
<li>core contracts</li>
<li>borrowed patterns</li>
</ul>
<p className="craik-product-card__meta">
<span>For: architects &middot; contributors</span>
<span className="craik-product-card__cta">4 min read</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">02</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Core concepts</p>
<h3 className="craik-section-banner__title">
Nine typed objects <em>every other doc speaks.</em>
</h3>
<p className="craik-section-banner__lede">
Each concept below maps to a runtime object the rest of the docs reference
by name. Read in order on a first pass — Build, Operate, and Secure all
assume you know what these are. Project model is foundational; everything
else composes on top.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../concepts/project-model/">
<div>
<p className="craik-product-feature__num">Foundation · 01</p>
<h4 className="craik-product-feature__title">Project model</h4>
<p className="craik-product-feature__summary">
The runner-readable view Craik builds from a registered repository.
Combines local configuration, repository state, documentation boundaries,
memory backend posture, policy posture, and known continuity records into
a single typed object every Craik component speaks. Case files, intent
locks, and onboarding payloads are all drawn against it.
</p>
<ul className="craik-product-feature__topics">
<li>mutable docs vs immutable evidence</li>
<li>policy posture</li>
<li>continuity</li>
<li>onboarding payload</li>
</ul>
<span className="craik-product-feature__cta">Read the project model</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Operational by design</p>
<p className="craik-product-feature__quote-text">
The model tells an agent which repository it is entering, which docs are
mutable, which paths are immutable evidence, which memory backend is
configured, and which next actions are currently allowed.
</p>
<p className="craik-product-feature__quote-attribution">— Project model · §Overview</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../concepts/case-files/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="10" width="36" height="44" rx="3" />
<line x1="20" y1="20" x2="44" y2="20" />
<line x1="20" y1="28" x2="40" y2="28" />
<line x1="20" y1="36" x2="44" y2="36" />
<line x1="20" y1="44" x2="36" y2="44" />
<circle cx="50" cy="14" r="4" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · Pre-run brief</p>
<h4 className="craik-product-card__title">Case files</h4>
<p className="craik-product-card__summary">
The per-task pre-run brief. Evidence, assumptions, stale-risk markers,
context-budget metadata, and a verification plan — sealed when built,
addressable for audit, and the input every runner reads first.
</p>
<blockquote className="craik-product-card__quote">
A case file is not a memory store, and it is not a transcript.
<span className="craik-product-card__quote-attr">Case files · §Definition</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>evidence</li>
<li>assumptions</li>
<li>context budget</li>
<li>verification plan</li>
</ul>
<p className="craik-product-card__meta">
<span>For: runners &middot; reviewers</span>
<span className="craik-product-card__cta">6 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/single-agent-loop/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="32" r="22" />
<line x1="32" y1="10" x2="32" y2="18" />
<line x1="54" y1="32" x2="46" y2="32" />
<line x1="32" y1="54" x2="32" y2="46" />
<line x1="10" y1="32" x2="18" y2="32" />
<circle cx="32" cy="32" r="3" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">03 · Bounded iteration</p>
<h4 className="craik-product-card__title">Single-agent execution loop</h4>
<p className="craik-product-card__summary">
Plan → Act → Observe → Evaluate → Continue or Stop. The v0.1 loop lets a
runner work through a governed task without depending on an untracked
chat transcript. Craik owns the durable boundary: run state, policy
checks, receipts, step outputs, and recovery context.
</p>
<blockquote className="craik-product-card__quote">
Side effects are policy-gated. A step such as shell execution must have
a matching capability grant before it runs.
<span className="craik-product-card__quote-attr">Single-agent loop · §Safety Boundaries</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>plan / act / observe / evaluate</li>
<li>step results</li>
<li>recovery</li>
<li>intent-lock checks</li>
</ul>
<p className="craik-product-card__meta">
<span>For: implementers</span>
<span className="craik-product-card__cta">4 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/receipts/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<path d="M 14 10 L 50 10 L 50 50 L 42 54 L 34 50 L 26 54 L 18 50 L 14 54 Z" />
<line x1="20" y1="20" x2="44" y2="20" />
<line x1="20" y1="28" x2="40" y2="28" />
<line x1="20" y1="36" x2="36" y2="36" />
<circle cx="44" cy="40" r="3" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">04 · Durable accountability</p>
<h4 className="craik-product-card__title">Receipts</h4>
<p className="craik-product-card__summary">
A concise, durable record for every action that mattered. Each receipt
names actor, credential, target, capability, reason, and result —
joinable by task, policy envelope, and handoff. Redaction guard runs on
every persistence path.
</p>
<blockquote className="craik-product-card__quote">
Every receipt names who acted, what they used, what they touched, why it
happened, and how it ended.
<span className="craik-product-card__quote-attr">Receipts · §Definition</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>actor + credential</li>
<li>redaction</li>
<li>task linkage</li>
<li>audit trail</li>
</ul>
<p className="craik-product-card__meta">
<span>For: auditors &middot; operators</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/handoffs/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="14" cy="32" r="6" />
<circle cx="50" cy="32" r="6" fill="var(--craik-lavender)" stroke="none" />
<line x1="22" y1="32" x2="42" y2="32" />
<path d="M 38 26 L 44 32 L 38 38" />
</svg>
<p className="craik-product-card__num">05 · Continuity</p>
<h4 className="craik-product-card__title">Handoffs</h4>
<p className="craik-product-card__summary">
Machine-readable run summaries the next agent — human or model — picks
up from. Status, completed actions, validation, assumptions, context
debt, policy exceptions, receipts, and memory proposals — plus a
self-audit checklist that keeps incomplete runs honest.
</p>
<blockquote className="craik-product-card__quote">
A handoff is not a transcript and not a chat log. It's the concise
continuity record that lets the next actor pick up.
<span className="craik-product-card__quote-attr">Handoffs · §Definition</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>structured + markdown</li>
<li>self-audit</li>
<li>policy exceptions</li>
<li>next-step contract</li>
</ul>
<p className="craik-product-card__meta">
<span>For: runners &middot; humans</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/work-graph/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="12" r="3.5" />
<circle cx="14" cy="32" r="3.5" />
<circle cx="50" cy="32" r="3.5" />
<circle cx="32" cy="52" r="3.5" fill="var(--craik-lavender)" stroke="none" />
<line x1="32" y1="16" x2="18" y2="28" />
<line x1="32" y1="16" x2="46" y2="28" />
<line x1="18" y1="36" x2="30" y2="48" />
<line x1="46" y1="36" x2="34" y2="48" />
</svg>
<p className="craik-product-card__num">06 · Connected state</p>
<h4 className="craik-product-card__title">Work graph</h4>
<p className="craik-product-card__summary">
A projection over the runtime objects already in <code>$CRAIK_HOME/state/</code>.
Tasks, case files, handoffs, receipts, memory proposals, evidence,
assumptions, and contradictions become queryable nodes connected by
typed edges. Deterministic, redacted, exportable.
</p>
<blockquote className="craik-product-card__quote">
The graph isn't a separate data store — it's a projection over the
existing typed objects in <code>$CRAIK_HOME/state/</code>.
<span className="craik-product-card__quote-attr">Work graph · §Definition</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>nodes &amp; edges</li>
<li>graph export</li>
<li>operator views</li>
<li>cross-cutting queries</li>
</ul>
<p className="craik-product-card__meta">
<span>For: reviewers</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/memory-and-stigmem/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="22" cy="22" r="10" />
<circle cx="42" cy="42" r="10" fill="var(--craik-lavender)" stroke="none" />
<line x1="30" y1="22" x2="42" y2="22" stroke-dasharray="3 3" />
<line x1="22" y1="30" x2="22" y2="42" stroke-dasharray="3 3" />
</svg>
<p className="craik-product-card__num">07 · Governed truth</p>
<h4 className="craik-product-card__title">Memory &amp; Stigmem</h4>
<p className="craik-product-card__summary">
Memory is governed project state, not a transcript cache. Agent-created
updates default to <em>proposals</em> with evidence; direct writes need
the <code>memory.write</code> grant. Craik owns orchestration; Stigmem
owns the durable fact substrate.
</p>
<blockquote className="craik-product-card__quote">
Agent-created memory updates default to proposals — durable, evidence-
backed candidate facts that remain reviewable until a human (or a policy
grant) promotes them.
<span className="craik-product-card__quote-attr">Memory &amp; Stigmem · §Proposal-First</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>proposal-first</li>
<li>evidence + scope</li>
<li>direct-write grant</li>
<li>Stigmem ownership</li>
</ul>
<p className="craik-product-card__meta">
<span>For: memory operators</span>
<span className="craik-product-card__cta">6 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/governance/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<path d="M 32 10 L 52 18 L 52 32 C 52 44 44 50 32 54 C 20 50 12 44 12 32 L 12 18 Z" />
<path d="M 24 32 L 30 38 L 42 26" />
<circle cx="32" cy="20" r="3" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">08 · Runtime guardrails</p>
<h4 className="craik-product-card__title">Governance</h4>
<p className="craik-product-card__summary">
Policy envelopes, capability grants, immutable paths, redaction, receipt
obligations, memory defaults, and the policy gate — all typed runtime
objects, not advisory configuration. Strict by default; fail-open is
opt-in only.
</p>
<blockquote className="craik-product-card__quote">
Craik treats governance as a runtime concern. Policy envelopes,
capability grants, and immutable paths are first-class records.
<span className="craik-product-card__quote-attr">Governance · §Definition</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>policy profiles</li>
<li>capability grants</li>
<li>fail-open</li>
<li>redaction</li>
</ul>
<p className="craik-product-card__meta">
<span>For: policy operators</span>
<span className="craik-product-card__cta">6 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../concepts/intent-locks/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="16" y="26" width="32" height="24" rx="3" />
<path d="M 22 26 L 22 18 C 22 14 26 10 32 10 C 38 10 42 14 42 18 L 42 26" />
<circle cx="32" cy="38" r="3" fill="var(--craik-lavender)" stroke="none" />
<line x1="32" y1="41" x2="32" y2="46" />
</svg>
<p className="craik-product-card__num">09 · Accepted scope</p>
<h4 className="craik-product-card__title">Intent locks</h4>
<p className="craik-product-card__summary">
The runtime's accepted interpretation of a task — explicit, durable, and
separate from the original request. In-scope, out-of-scope, allowed
autonomy, stop conditions, and scope-change rules. Every case file and
handoff carries the lock id.
</p>
<blockquote className="craik-product-card__quote">
The lock is what the runtime committed to before the work began — every
later decision can be checked against it.
<span className="craik-product-card__quote-attr">Intent locks · §Why bother?</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>accepted interpretation</li>
<li>in-scope / out-of-scope</li>
<li>stop conditions</li>
<li>scope-change rules</li>
</ul>
<p className="craik-product-card__meta">
<span>For: task owners</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">03</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Runtime contracts</p>
<h3 className="craik-section-banner__title">
The typed spine <em>every component speaks.</em>
</h3>
<p className="craik-section-banner__lede">
Six contracts the runtime persists, versions, and validates. Adapters,
memory backends, and future plugins integrate through these — break one
and the policy gate fails closed. Read this when you need to write a
policy, ship an adapter, or interpret a receipt.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../runtime-contracts/">
<div>
<p className="craik-product-feature__num">Foundation · 01</p>
<h4 className="craik-product-feature__title">Runtime contracts overview</h4>
<p className="craik-product-feature__summary">
The product spine. Every persisted contract carries
<code>schema</code> and <code>version</code> fields; breaking changes
require a new version and a migration path. Task requests, case files,
policy envelopes, capability grants, capability receipts, handoffs,
proposed facts, contradiction reports, verification results, and
work-graph events — all live here.
</p>
<ul className="craik-product-feature__topics">
<li>versioning</li>
<li>shape examples</li>
<li>migration policy</li>
<li>adapter integration</li>
</ul>
<span className="craik-product-feature__cta">Read the contracts</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Why a spine</p>
<p className="craik-product-feature__quote-text">
Craik should be built around stable, versioned contracts. The contracts
are the product spine: adapters, agents, memory backends, and future
plugins should integrate through them.
</p>
<p className="craik-product-feature__quote-attribution">— Runtime contracts · §Intro</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../reference/schemas/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="14" width="36" height="36" rx="2" />
<line x1="14" y1="22" x2="50" y2="22" />
<line x1="14" y1="30" x2="50" y2="30" />
<line x1="14" y1="38" x2="50" y2="38" />
<circle cx="22" cy="18" r="1.6" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · Strict typing</p>
<h4 className="craik-product-card__title">Schemas</h4>
<p className="craik-product-card__summary">
Every contract is a strict Pydantic model. <code>craik schema list</code>
enumerates them; <code>craik schema show &lt;name&gt;</code> prints JSON
Schema. Unknown fields are rejected so adapters and plugins can't
silently depend on accidental payload shape.
</p>
<blockquote className="craik-product-card__quote">
Unknown fields are rejected so adapters, memory backends, and future
plugins do not silently depend on accidental payload shape.
<span className="craik-product-card__quote-attr">Schemas · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>pydantic models</li>
<li>schema CLI</li>
<li>JSON Schema export</li>
<li>strict validation</li>
</ul>
<p className="craik-product-card__meta">
<span>For: integrators</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../reference/project-profile/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="14" width="36" height="36" rx="3" />
<path d="M 22 24 L 30 24 L 32 28 L 42 28 L 42 38 L 22 38 Z" />
<circle cx="46" cy="44" r="2.5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">03 · Repo wiring</p>
<h4 className="craik-product-card__title">Project profile</h4>
<p className="craik-product-card__summary">
The <code>craik.project_profile</code> shape: stable id, repo paths,
default branch, docs and immutable paths, memory backend and scope.
Inputs to every case-file build and onboarding payload.
</p>
<blockquote className="craik-product-card__quote">
Project profiles describe repositories Craik can reason about.
<span className="craik-product-card__quote-attr">Project profile · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>repo metadata</li>
<li>docs boundaries</li>
<li>memory backend</li>
<li>git detection</li>
</ul>
<p className="craik-product-card__meta">
<span>For: operators</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../reference/run-state/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="14" cy="32" r="3" />
<circle cx="32" cy="32" r="3" />
<circle cx="50" cy="32" r="3" fill="var(--craik-lavender)" stroke="none" />
<line x1="17" y1="32" x2="29" y2="32" />
<line x1="35" y1="32" x2="47" y2="32" />
<rect x="22" y="14" width="20" height="8" rx="2" />
<rect x="22" y="42" width="20" height="8" rx="2" />
</svg>
<p className="craik-product-card__num">04 · Inspectable runs</p>
<h4 className="craik-product-card__title">Run state</h4>
<p className="craik-product-card__summary">
<code>craik.task_run</code> links task request, case file, policy
envelope, runner identity, intent lock, receipts, and final handoff.
Status (<code>pending → running → completed/blocked/failed/interrupted</code>)
and phase (<code>plan/act/observe/evaluate/continue/stop</code>) are
both first-class fields.
</p>
<blockquote className="craik-product-card__quote">
It gives later loop orchestration an inspectable record without
depending on an untracked chat transcript.
<span className="craik-product-card__quote-attr">Run state · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>task_run</li>
<li>status + phase</li>
<li>recovery</li>
<li>step results</li>
</ul>
<p className="craik-product-card__meta">
<span>For: implementers</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../reference/worker-results/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="14" r="4" />
<rect x="16" y="26" width="32" height="8" rx="2" />
<rect x="12" y="40" width="18" height="8" rx="2" />
<rect x="34" y="40" width="18" height="8" rx="2" fill="var(--craik-lavender)" stroke="none" />
<line x1="32" y1="18" x2="32" y2="26" />
<line x1="22" y1="34" x2="22" y2="40" />
<line x1="42" y1="34" x2="42" y2="40" />
</svg>
<p className="craik-product-card__num">05 · Typed specialist output</p>
<h4 className="craik-product-card__title">Worker results</h4>
<p className="craik-product-card__summary">
<code>craik.worker_result</code> preserves role-specific specialist
output: findings with severity and evidence, artifacts, assumptions,
risks, proposed actions, contradiction ids, receipts, diagnostics.
Conflicting specialist outputs stay conflicting — review decides later.
</p>
<blockquote className="craik-product-card__quote">
Specialist outputs should remain typed even when agents disagree. Do
not flatten conflicting results into a single consensus.
<span className="craik-product-card__quote-attr">Worker results · §Typed outputs</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>typed findings</li>
<li>severity + evidence</li>
<li>contradiction preservation</li>
<li>multi-agent</li>
</ul>
<p className="craik-product-card__meta">
<span>For: orchestration</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../reference/failure-modes/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<path d="M 32 10 L 54 50 L 10 50 Z" />
<line x1="32" y1="26" x2="32" y2="38" />
<circle cx="32" cy="44" r="2.2" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">06 · MVP hardening</p>
<h4 className="craik-product-card__title">Failure modes</h4>
<p className="craik-product-card__summary">
The fail-closed posture. Prompt-injection containment, secret rejection
at persistence, denied-capability handling, fail-open visibility,
automation stops, recovery requirements — and an explicit list of paths
the MVP does <em>not</em> claim (live provider calls as default, broad
daemon mode, dashboards, direct durable memory writes).
</p>
<blockquote className="craik-product-card__quote">
The runtime should preserve enough state to recover or review a failed
run without silently promoting uncertain work to durable facts.
<span className="craik-product-card__quote-attr">Failure modes · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>fail-closed</li>
<li>prompt injection</li>
<li>secret rejection</li>
<li>MVP boundaries</li>
</ul>
<p className="craik-product-card__meta">
<span>For: security &middot; reviewers</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">04</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Status &amp; roadmap</p>
<h3 className="craik-section-banner__title">
Where Craik is today — <em>and where it is going.</em>
</h3>
<p className="craik-section-banner__lede">
Honest about what's not yet built. Six docs together describe the
active MVP boundary, the upcoming releases, the current end-to-end
surfaces, and the gates an item must clear before it ships.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../mvp-roadmap/">
<div>
<p className="craik-product-feature__num">Active · 01</p>
<h4 className="craik-product-feature__title">MVP roadmap</h4>
<p className="craik-product-feature__summary">
The robust <code>0.x.0</code> MVP target — not <code>1.0.0</code>. Names
the readiness work that affects trust, release hygiene, documentation
accuracy, provider support, and package publication. Read this when you
want to know what blocks the first public release.
</p>
<ul className="craik-product-feature__topics">
<li>OIDC operator identity</li>
<li>credential profiles</li>
<li>OpenAI + Anthropic support</li>
<li>release gates</li>
</ul>
<span className="craik-product-feature__cta">Read the MVP roadmap</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Definition of done</p>
<p className="craik-product-feature__quote-text">
The MVP is complete when Craik can run one real software-delivery
workflow end to end with OIDC-authenticated operators, typed credential
profiles, policy-enforced side effects, durable receipts, a useful
handoff, accurate documentation, and package-release quality gates.
</p>
<p className="craik-product-feature__quote-attribution">— MVP roadmap · §MVP Definition</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../mvp/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="32" r="22" />
<circle cx="32" cy="32" r="12" />
<circle cx="32" cy="32" r="4" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · One workflow</p>
<h4 className="craik-product-card__title">MVP plan</h4>
<p className="craik-product-card__summary">
The original MVP scope: prove one complete workflow instead of a broad
platform shell. The accepted primary demo is Stigmem documentation and
state reconciliation — the workflow CI exercises end-to-end.
</p>
<blockquote className="craik-product-card__quote">
The MVP should prove one complete workflow instead of building a broad
platform shell.
<span className="craik-product-card__quote-attr">MVP plan · §MVP Goal</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>stigmem demo</li>
<li>governed workflow</li>
<li>handoff backed by memory</li>
<li>capability receipts</li>
</ul>
<p className="craik-product-card__meta">
<span>For: contributors</span>
<span className="craik-product-card__cta">Read MVP</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../roadmap/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<line x1="10" y1="32" x2="54" y2="32" />
<circle cx="14" cy="32" r="3" fill="var(--craik-lavender)" stroke="none" />
<circle cx="28" cy="32" r="3" />
<circle cx="42" cy="32" r="3" />
<circle cx="54" cy="32" r="3" />
<line x1="14" y1="14" x2="14" y2="50" stroke-dasharray="2 3" />
</svg>
<p className="craik-product-card__num">03 · Long view</p>
<h4 className="craik-product-card__title">Roadmap</h4>
<p className="craik-product-card__summary">
The broader trajectory: smallest useful runtime first, then Stigmem-
native memory, runner adapters, multi-agent coordination, instruction
distillation, community extensions. Seven roadmap rules keep features
from shipping without docs, evidence, and policy posture.
</p>
<blockquote className="craik-product-card__quote">
Every roadmap item must produce implementation, tests or validation,
and documentation. Craik should not ship features that only exist as
code or only exist as strategy.
<span className="craik-product-card__quote-attr">Roadmap · §Roadmap Rules</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>seven rules</li>
<li>CLI first</li>
<li>evidence before memory</li>
<li>strict-by-default</li>
</ul>
<p className="craik-product-card__meta">
<span>For: anyone</span>
<span className="craik-product-card__cta">Read roadmap</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../release-readiness/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="14" width="36" height="36" rx="3" />
<path d="M 22 32 L 30 40 L 44 24" />
<circle cx="48" cy="48" r="3" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">04 · Pass / fail snapshot</p>
<h4 className="craik-product-card__title">Release readiness · v0.1.0</h4>
<p className="craik-product-card__summary">
The concrete checklist validated on 2026-05-17 against <code>main</code>.
CI green, CodeQL green, schema and contract regressions verified.
Repository-owned readiness is complete; remaining work is the protected
publication process at tag time.
</p>
<blockquote className="craik-product-card__quote">
Repository-owned readiness checks are complete. The remaining work is
outside the repository: create the <code>v0.1.0</code> tag and run the
protected publication process when the maintainer is ready.
<span className="craik-product-card__quote-attr">Release readiness · §Summary</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>CI green</li>
<li>CodeQL green</li>
<li>schema regressions</li>
<li>publication gate</li>
</ul>
<p className="craik-product-card__meta">
<span>For: maintainers</span>
<span className="craik-product-card__cta">Snapshot</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../limitations/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="10" y="14" width="44" height="36" rx="3" />
<line x1="14" y1="22" x2="40" y2="22" />
<line x1="14" y1="30" x2="34" y2="30" />
<line x1="14" y1="38" x2="44" y2="38" />
<path d="M 36 14 L 50 28" stroke-dasharray="3 3" />
<path d="M 50 14 L 36 28" stroke-dasharray="3 3" />
<circle cx="42" cy="44" r="2.5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">05 · What's not yet</p>
<h4 className="craik-product-card__title">Limitations</h4>
<p className="craik-product-card__summary">
The honest scope boundary. Lists the v0.1 end-to-end surfaces that
work today (home init, project registration, case-file assembly, local
state inspection, policy gates, foreground gateway health service)
and the deliberately post-MVP surfaces (hosted gateway dispatch,
operator dashboards, broad live tool execution).
</p>
<blockquote className="craik-product-card__quote">
Several surfaces are not yet end-to-end production workflows.
<span className="craik-product-card__quote-attr">Limitations · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>working today</li>
<li>post-MVP scope</li>
<li>v0.12 contract coverage</li>
<li>honesty boundary</li>
</ul>
<p className="craik-product-card__meta">
<span>For: everyone</span>
<span className="craik-product-card__cta">Honest scope</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../implementation-plan/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="14" width="36" height="8" rx="1" />
<rect x="14" y="26" width="28" height="8" rx="1" />
<rect x="14" y="38" width="34" height="8" rx="1" />
<rect x="14" y="50" width="24" height="6" rx="1" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">06 · How it gets built</p>
<h4 className="craik-product-card__title">Implementation plan</h4>
<p className="craik-product-card__summary">
The accepted stack and build sequence. Python 3.12+, Typer CLI, Pydantic
schemas, SQLite for local state, stdlib HTTP for first integrations,
<code>pytest</code> for tests, ruff and mypy for quality. The sequence
of milestones that gets v0.1 to release.
</p>
<blockquote className="craik-product-card__quote">
This plan turns the Craik concept into a buildable sequence.
<span className="craik-product-card__quote-attr">Implementation plan · §Intro</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>python 3.12+</li>
<li>typer + pydantic</li>
<li>milestones</li>
<li>quality gates</li>
</ul>
<p className="craik-product-card__meta">
<span>For: contributors</span>
<span className="craik-product-card__cta">Build plan</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">05</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Architecture decisions</p>
<h3 className="craik-section-banner__title">
The reasons behind <em>the structural choices.</em>
</h3>
<p className="craik-section-banner__lede">
ADRs record durable design decisions separately from mutable reference
material. Reference docs describe current behavior; ADRs explain why
the shape exists, what tradeoffs were accepted, and how a decision can
be retracted.
</p>
</div>
</header>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../adr/record-mvp-runner-scope/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0001</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">MVP runner scope</h4>
<p className="craik-adr-card__decision">
Sets the public framing: the MVP ships case-file assembly, policy
envelopes, prompt compilation, receipts, handoffs, and one governed
workflow — not unbounded tool execution.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/provider-transport-and-mode-families/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0002</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Provider transport &amp; mode families</h4>
<p className="craik-adr-card__decision">
OpenAI Responses, Anthropic Messages, and OAI-compatible Chat
Completions stay as separate transport families — not collapsed into a
single adapter — so tool, streaming, usage, and retry differences stay
explicit.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/secret-handling/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0003</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Secret handling</h4>
<p className="craik-adr-card__decision">
Receipts, handoffs, case files, provider configs, and local store
records are scrubbed through a central redaction guard before
persistence. Secret material is referenced — never copied.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/policy-envelope-shape/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0004</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Policy envelope shape</h4>
<p className="craik-adr-card__decision">
The policy envelope binds actor, task, profile, grant requirements,
redaction posture, and receipt obligations into one typed record that
travels with every governed action.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/receipts-and-handoffs-as-public-contracts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0005</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Receipts &amp; handoffs as public contracts</h4>
<p className="craik-adr-card__decision">
Receipts and handoffs sit at the boundary of runtime, memory, docs, and
operator workflows. They are versioned public contracts — adapters and
plugins integrate against them without renegotiating shape.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/package-and-runtime-layout/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0006</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Package &amp; runtime layout</h4>
<p className="craik-adr-card__decision">
Splits the historically flat runtime namespace into ownership-bearing
modules (providers, memory, policy, work execution, companions,
channels, voice, sandboxing, project workflows) so change rates and
risk profiles can diverge cleanly.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/credential-and-identity-architecture/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0007</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Credential &amp; identity architecture</h4>
<p className="craik-adr-card__decision">
Provider credentials and operator identity are governance inputs.
Every receipt names which human authorized work, which credential
carried the call, which policy allowed it, and which grant made the
credential usable.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../adr/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">Index</span>
<span className="craik-adr-card__status">Catalog</span>
</div>
<h4 className="craik-adr-card__title">ADR index</h4>
<p className="craik-adr-card__decision">
The full catalog of accepted decisions and the conventions for
proposing new ones, retiring old ones, and citing them from reference
docs.
</p>
<span className="craik-adr-card__cta">Browse all</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">06</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Stigmem integration</p>
<h3 className="craik-section-banner__title">
The reference memory substrate — <em>and the boundary.</em>
</h3>
<p className="craik-section-banner__lede">
Craik runs in degraded local mode without Stigmem, but Stigmem is the
reference substrate for team-scale memory. One doc draws the exact
boundary between what Craik owns and what Stigmem owns.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../stigmem-integration/">
<div>
<p className="craik-product-feature__num">Substrate · 01</p>
<h4 className="craik-product-feature__title">Stigmem integration</h4>
<p className="craik-product-feature__summary">
Stigmem owns facts, provenance, scopes, trust metadata, contradiction
tracking, federation, auth, and memory plugin hooks. Craik owns
orchestration, case files, agent roles, capability grants, receipts,
handoffs, and project workflows. Each side stays focused; the contract
between them is the proposal flow plus a small set of read APIs.
</p>
<ul className="craik-product-feature__topics">
<li>ownership boundary</li>
<li>fact substrate</li>
<li>federation</li>
<li>read APIs</li>
</ul>
<span className="craik-product-feature__cta">Read the integration</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Substrate</p>
<p className="craik-product-feature__quote-text">
Craik should use Stigmem as its reference memory and truth substrate.
</p>
<p className="craik-product-feature__quote-attribution">— Stigmem integration · §Boundary</p>
</blockquote>
</a>

</div>

## Where to go next

Once the concepts are clear, choose your path:

- **Install and run something** → [Build · Getting started](guides/installation.md)
- **Integrate a runner or provider** → [Build · Connecting runners](reference/runner-adapter-contract.md)
- **Govern execution** → [Secure · Governance fundamentals](concepts/governance.md)
- **Run and inspect the system** → [Operate · Operator views](reference/operator-surface.md)
