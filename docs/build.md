---
id: build
title: Build
sidebar_label: Overview
sidebar_position: 0
description: Install Craik, register projects, connect runners and providers, and put the runtime to work.
slug: /build
---

# Build with Craik

This section is task-oriented. Every page either gets you to a running Craik
surface or documents a contract you implement against. Topics are grouped by
**what you are trying to build**, and each group lists the guides and reference
in the order most teams reach for them.

If you've never seen Craik before, do these three things first:

1. [Install Craik](guides/installation.md)
2. [Quickstart](guides/quickstart.md)
3. [Register a project](guides/project-registry.md)

## Implementation paths

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">01</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Getting started</p>
<h3 className="craik-section-banner__title">
From zero to a <em>governed first run.</em>
</h3>
<p className="craik-section-banner__lede">
Install the CLI, point it at a repository, initialize the home
directory, and walk a complete governed task — without making a single
live provider call. Four docs, in order.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/quickstart/">
<div>
<p className="craik-product-feature__num">Hands-on · 01</p>
<h4 className="craik-product-feature__title">Quickstart</h4>
<p className="craik-product-feature__summary">
A 10-minute narrative tutorial: sandbox the Craik home, register a
project, create a task, build a case file, run the policy gate, emit a
handoff, and inspect what landed on disk. Uses the fixture-backed
provider path — zero credentials, zero network.
</p>
<ul className="craik-product-feature__topics">
<li>sandboxed home</li>
<li>case file + policy gate</li>
<li>handoff</li>
<li>stigmem demo</li>
</ul>
<span className="craik-product-feature__cta">Walk the quickstart</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">What you'll do</p>
<p className="craik-product-feature__quote-text">
Install Craik, point it at a Git repository, build a case file, run
policy tests, and emit a handoff — without making a single live
provider call. Every output we discuss is real and persists on disk.
</p>
<p className="craik-product-feature__quote-attribution">— Quickstart · §What you'll do</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../guides/installation/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="20" width="36" height="28" rx="3" />
<path d="M 32 14 L 32 30" />
<path d="M 26 24 L 32 30 L 38 24" />
<circle cx="20" cy="42" r="2" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · Front door</p>
<h4 className="craik-product-card__title">Installation</h4>
<p className="craik-product-card__summary">
Prerequisites, three install paths (<code>pipx</code> / <code>pip</code>
/ source), verification commands, home initialization, optional auth,
and a troubleshooting matrix for the most common first-run issues.
</p>
<blockquote className="craik-product-card__quote">
Craik is a Python CLI. You need a recent Python interpreter and a way
to put the CLI on your PATH.
<span className="craik-product-card__quote-attr">Installation · §Prerequisites</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>python 3.12+</li>
<li>pipx / pip</li>
<li>verification</li>
<li>troubleshooting</li>
</ul>
<p className="craik-product-card__meta">
<span>For: everyone</span>
<span className="craik-product-card__cta">3 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../guides/setup/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="32" cy="32" r="14" />
<circle cx="32" cy="32" r="6" fill="var(--craik-lavender)" stroke="none" />
<line x1="32" y1="10" x2="32" y2="18" />
<line x1="54" y1="32" x2="46" y2="32" />
<line x1="32" y1="54" x2="32" y2="46" />
<line x1="10" y1="32" x2="18" y2="32" />
</svg>
<p className="craik-product-card__num">03 · Wire it up</p>
<h4 className="craik-product-card__title">Setup wizard</h4>
<p className="craik-product-card__summary">
<code>craik setup</code> initializes the local home, the SQLite store,
and a default gateway configuration. Writes inspectable, non-secret
configuration only. Authentication and credentials are added separately
after setup completes.
</p>
<blockquote className="craik-product-card__quote">
The wizard writes inspectable, non-secret configuration only. It does
not ask for API keys, channel tokens, webhook secrets, or bearer
credentials.
<span className="craik-product-card__quote-attr">Setup · §Secrets-free</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>home init</li>
<li>local store</li>
<li>gateway config</li>
<li>secrets-free</li>
</ul>
<p className="craik-product-card__meta">
<span>For: first-time operators</span>
<span className="craik-product-card__cta">4 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../guides/configuring-craik-home/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<path d="M 14 30 L 32 14 L 50 30 L 50 50 L 14 50 Z" />
<rect x="22" y="34" width="20" height="16" />
<circle cx="46" cy="20" r="2.5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">04 · Where state lives</p>
<h4 className="craik-product-card__title">Configuring Craik home</h4>
<p className="craik-product-card__summary">
The default <code>~/.craik/</code> layout, overrides via
<code>CRAIK_HOME</code>, share patterns for CI runners and containerized
runs, and the reset procedure. Read this before pointing Craik at a
network share.
</p>
<blockquote className="craik-product-card__quote">
Craik does NOT silently create project-local <code>.craik/</code>
directories inside your repositories.
<span className="craik-product-card__quote-attr">Configuring home · §Default location</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>home layout</li>
<li>CRAIK_HOME</li>
<li>CI runners</li>
<li>reset</li>
</ul>
<p className="craik-product-card__meta">
<span>For: operators</span>
<span className="craik-product-card__cta">4 min read</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">02</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Working with projects</p>
<h3 className="craik-section-banner__title">
Repositories become <em>typed, queryable projects.</em>
</h3>
<p className="craik-section-banner__lede">
The project profile is the durable representation of a repository.
Case files are the per-task brief built from it. Handoffs are how runs
end. These four docs cover the full project-to-handoff lifecycle.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/project-registry/">
<div>
<p className="craik-product-feature__num">Entry point · 01</p>
<h4 className="craik-product-feature__title">Project registry</h4>
<p className="craik-product-feature__summary">
Register a Git repository as a Craik project. Declares mutable docs
paths, immutable evidence paths, and (optionally) a memory backend.
Project records persist in the local SQLite store — Craik never writes
into your repository.
</p>
<ul className="craik-product-feature__topics">
<li>boundaries</li>
<li>multi-project</li>
<li>inspect via onboard</li>
<li>local-only state</li>
</ul>
<span className="craik-product-feature__cta">Register a project</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Where state lives</p>
<p className="craik-product-feature__quote-text">
Registration writes only to Craik local state under <code>~/.craik</code>
or <code>$CRAIK_HOME</code>. It does not create project-local
<code>.craik/</code> metadata inside the repository.
</p>
<p className="craik-product-feature__quote-attribution">— Project registry · §Where state lives</p>
</blockquote>
</a>

<ol className="craik-product-list">

<li>
<a className="craik-product-card" href="../reference/project-profile/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<rect x="14" y="14" width="36" height="36" rx="2" />
<line x1="14" y1="22" x2="50" y2="22" />
<line x1="20" y1="30" x2="44" y2="30" />
<line x1="20" y1="36" x2="40" y2="36" />
<line x1="20" y1="42" x2="44" y2="42" />
<circle cx="18" cy="18" r="1.5" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">02 · Typed object</p>
<h4 className="craik-product-card__title">Project profile reference</h4>
<p className="craik-product-card__summary">
The <code>craik.project_profile</code> shape: stable id, repo paths,
default branch, docs and immutable paths, memory backend and scope.
Every case-file build and onboarding payload reads against this.
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
<span>For: integrators</span>
<span className="craik-product-card__cta">Reference</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../guides/using-case-files/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<path d="M 14 14 L 14 50 L 50 50 L 50 22 L 42 14 Z" />
<path d="M 42 14 L 42 22 L 50 22" />
<line x1="22" y1="32" x2="42" y2="32" />
<line x1="22" y1="38" x2="38" y2="38" />
<line x1="22" y1="44" x2="42" y2="44" />
<circle cx="46" cy="46" r="2" fill="var(--craik-lavender)" stroke="none" />
</svg>
<p className="craik-product-card__num">03 · Pre-run brief</p>
<h4 className="craik-product-card__title">Using case files</h4>
<p className="craik-product-card__summary">
Build, inspect, and refresh per-task case files. Discovery overrides,
the 10 fields to review before authorizing a run, and how to handle
open assumptions as first-class — not bugs.
</p>
<blockquote className="craik-product-card__quote">
Case files are only as good as the project they're built against.
<span className="craik-product-card__quote-attr">Using case files · §Tune discovery</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>case build</li>
<li>discovery overrides</li>
<li>assumptions</li>
<li>refresh procedure</li>
</ul>
<p className="craik-product-card__meta">
<span>For: operators</span>
<span className="craik-product-card__cta">6 min read</span>
</p>
</a>
</li>

<li>
<a className="craik-product-card" href="../guides/writing-handoffs/">
<svg className="craik-card-motif" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="16" cy="32" r="5" />
<circle cx="48" cy="32" r="5" fill="var(--craik-lavender)" stroke="none" />
<line x1="22" y1="32" x2="40" y2="32" />
<path d="M 36 26 L 42 32 L 36 38" />
<rect x="10" y="48" width="44" height="6" rx="1" />
</svg>
<p className="craik-product-card__num">04 · Continuity</p>
<h4 className="craik-product-card__title">Writing handoffs</h4>
<p className="craik-product-card__summary">
Status semantics (<code>completed/incomplete/blocked/failed</code>),
the eight things every handoff should include, anti-patterns that hurt
the next agent, and the six self-audit checks that keep incomplete
runs honest.
</p>
<blockquote className="craik-product-card__quote">
Incomplete handoffs are valid. Dishonest handoffs are not — they
contaminate the next run's context.
<span className="craik-product-card__quote-attr">Writing handoffs · §Self-audit</span>
</blockquote>
<ul className="craik-product-card__topics">
<li>status semantics</li>
<li>anti-patterns</li>
<li>self-audit</li>
<li>continuity</li>
</ul>
<p className="craik-product-card__meta">
<span>For: runners &middot; humans</span>
<span className="craik-product-card__cta">5 min read</span>
</p>
</a>
</li>

</ol>

</div>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">03</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Connecting a runner</p>
<h3 className="craik-section-banner__title">
Codex, Claude, Gemini — <em>or your own.</em>
</h3>
<p className="craik-section-banner__lede">
Every runner consumes the same Craik contracts. The runner-adapter
boundary is intentionally runner-agnostic: adapters receive Craik state
and return normalized Craik state without leaking provider-specific
details into core. Eleven docs cover the contract, the three preview
adapters that ship today, and the workflows around them.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/runner-adapter-contract/">
<div>
<p className="craik-product-feature__num">Protocol · 01</p>
<h4 className="craik-product-feature__title">Runner adapter contract</h4>
<p className="craik-product-feature__summary">
The protocol every runner adapter implements. Defines the boundary
where Craik core hands off compiled prompts and policy envelopes, and
where the runner returns normalized worker results, receipts, and
handoff metadata.
</p>
<ul className="craik-product-feature__topics">
<li>RunnerAdapter protocol</li>
<li>compiled prompt boundary</li>
<li>normalized return</li>
<li>v0.1 preview adapters</li>
</ul>
<span className="craik-product-feature__cta">Read the contract</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Boundary</p>
<p className="craik-product-feature__quote-text">
Adapters receive Craik state and return normalized Craik state without
leaking provider-specific details into core contracts.
</p>
<p className="craik-product-feature__quote-attribution">— Runner adapter contract · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/runner-step-contracts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract</span>
</div>
<h4 className="craik-adr-card__title">Runner step contracts</h4>
<p className="craik-adr-card__decision">
Each phase (<code>plan / act / observe / evaluate / continue / stop</code>)
is a typed step request and step result — invoked by the loop, not the
runner itself.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/runner-metadata/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract</span>
</div>
<h4 className="craik-adr-card__title">Runner metadata</h4>
<p className="craik-adr-card__decision">
Captured at adapter boundaries so receipts and handoffs can explain
which runner produced work without adding provider-specific fields to
the stable contract surface.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/codex-runner-adapter/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · preview</span>
</div>
<h4 className="craik-adr-card__title">Codex runner adapter</h4>
<p className="craik-adr-card__decision">
Conservative v0.1 preview. Turns a compiled prompt into a normalized
runner request and returns deterministic fixture results when live
execution is unavailable.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/claude-runner-adapter/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · preview</span>
</div>
<h4 className="craik-adr-card__title">Claude runner adapter</h4>
<p className="craik-adr-card__decision">
Focuses on prompt handoff and deterministic fixture output. Live
external execution is a later milestone in the adapter roadmap.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/gemini-runner-adapter/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter · preview</span>
</div>
<h4 className="craik-adr-card__title">Gemini runner adapter</h4>
<p className="craik-adr-card__decision">
Read/review-oriented in v0.1. Uses prompt handoff plus deterministic
fixture output rather than direct external execution; full live
adapter is post-MVP.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/runner-preview-workflows/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Workflow</span>
</div>
<h4 className="craik-adr-card__title">Runner preview workflows</h4>
<p className="craik-adr-card__decision">
Threads the four pieces together: context discovery, policy-aware
prompt compilation, runner fixture or prompt-handoff execution, and
receipt-plus-handoff metadata capture.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/single-agent-fixture-loop/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">08</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Workflow</span>
</div>
<h4 className="craik-adr-card__title">Single-agent fixture loop</h4>
<p className="craik-adr-card__decision">
Smoke-test the loop boundary without live runner credentials or
external side effects. The pattern CI uses for every PR.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/agent-roles/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">09</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Reference · v0.3</span>
</div>
<h4 className="craik-adr-card__title">Agent roles</h4>
<p className="craik-adr-card__decision">
<code>craik.agent_role</code> defines the role boundary for v0.3
multi-agent coordination. Roles describe responsibility and authority;
they do not grant new runtime permissions by themselves.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/adapter-packages/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">10</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Reference</span>
</div>
<h4 className="craik-adr-card__title">Adapter packages</h4>
<p className="craik-adr-card__decision">
The <code>craik.adapter_package</code> contract records adapter
identity, package version, implementation entrypoints, and the metadata
plugin discovery uses.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/worker-results/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">11</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract</span>
</div>
<h4 className="craik-adr-card__title">Worker results</h4>
<p className="craik-adr-card__decision">
<code>craik.worker_result</code> preserves typed specialist output:
findings, artifacts, assumptions, risks, contradiction ids, receipts.
Conflicts stay conflicting — review decides later.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">04</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Connecting a provider</p>
<h3 className="craik-section-banner__title">
The transport sits <em>under</em> the runner.
</h3>
<p className="craik-section-banner__lede">
Provider transport is independent of the runner: OpenAI Responses,
Anthropic Messages, and OAI-compatible Chat Completions are separate
transport families. Seven docs cover the model-provider contract,
routing decisions, the operator CLI surface, failover policy,
certification, identity, and prompt compilation.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/model-providers/">
<div>
<p className="craik-product-feature__num">Contract · 01</p>
<h4 className="craik-product-feature__title">Model providers</h4>
<p className="craik-product-feature__summary">
The <code>craik.model_provider</code> contract records model and
runtime metadata used for routing. Provider transport is selected per
call — fixture, local OAI-compatible, or hosted (OpenAI Responses /
Anthropic Messages). Design rationale lives in
<a href="../adr/provider-transport-and-mode-families/">ADR 0002</a>.
</p>
<ul className="craik-product-feature__topics">
<li>transport families</li>
<li>routing metadata</li>
<li>OAI-compatible servers</li>
<li>ADR 0002</li>
</ul>
<span className="craik-product-feature__cta">Read the contract</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Routing input</p>
<p className="craik-product-feature__quote-text">
<code>craik.model_provider</code> records model provider and runtime
execution path metadata for provider routing.
</p>
<p className="craik-product-feature__quote-attribution">— Model providers · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/provider-routing/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guide</span>
</div>
<h4 className="craik-adr-card__title">Provider routing &amp; sandboxes</h4>
<p className="craik-adr-card__decision">
Routing chooses model/runtime metadata. Sandbox routing chooses an
execution environment. Keep those decisions separate so policy,
receipts, and redaction can audit each boundary independently.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/provider-switching/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">CLI</span>
</div>
<h4 className="craik-adr-card__title">Provider switching</h4>
<p className="craik-adr-card__decision">
<code>craik provider</code> exposes the operator-facing surface for
model/provider routing — list, show, and switch the active provider
within the bounds the policy envelope allows.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/provider-failover/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Policy</span>
</div>
<h4 className="craik-adr-card__title">Provider failover</h4>
<p className="craik-adr-card__decision">
Failover is an explicit routing policy. Craik only falls back from one
provider to another when a <code>ProviderFailoverPolicy</code> rule
matches — every fallback preserves the active policy envelope id.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/provider-certification/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">MVP bar</span>
</div>
<h4 className="craik-adr-card__title">Provider certification</h4>
<p className="craik-adr-card__decision">
OpenAI and Anthropic share one certification bar. Provider metadata
alone is not enough; a provider is MVP-ready only when tests and
receipts show the runtime can safely use it in a governed workflow.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/authentication/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Identity</span>
</div>
<h4 className="craik-adr-card__title">Authentication &amp; credentials</h4>
<p className="craik-adr-card__decision">
Operator identity (OIDC) is separate from credential identity (the
provider account used for model calls). Every receipt records both —
audit can answer "who authorized this" and "which credential carried
it out" without inspecting secret material.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/prompt-compiler/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Tool</span>
</div>
<h4 className="craik-adr-card__title">Prompt compiler</h4>
<p className="craik-adr-card__decision">
<code>craik prompt compile</code> turns Craik runtime state into a
deterministic runner-ready prompt. It does not invoke a runner — it
prepares the prompt boundary for adapter previews.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">05</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Connecting memory &amp; Stigmem</p>
<h3 className="craik-section-banner__title">
Local SQLite by default — <em>Stigmem for team-scale memory.</em>
</h3>
<p className="craik-section-banner__lede">
Craik runs in degraded local mode against the SQLite store at
<code>$CRAIK_HOME/state/craik.sqlite</code>. When you need durable,
shared team memory you connect a Stigmem node through the minimum
v0.1 HTTP endpoint surface. Six docs cover the integration, the demo,
and the contracts beneath.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/connecting-stigmem/">
<div>
<p className="craik-product-feature__num">Wire it up · 01</p>
<h4 className="craik-product-feature__title">Connecting Stigmem</h4>
<p className="craik-product-feature__summary">
Point Craik at a Stigmem node via <code>CRAIK_STIGMEM_URL</code> and,
when the node requires it, a bearer API key. The integration uses the
minimum v0.1 HTTP surface — health, capability discovery, fact read,
and fact provenance — without printing credentials.
</p>
<ul className="craik-product-feature__topics">
<li>HTTP endpoints</li>
<li>capability discovery</li>
<li>bearer auth</li>
<li>read APIs</li>
</ul>
<span className="craik-product-feature__cta">Connect Stigmem</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Minimum surface</p>
<p className="craik-product-feature__quote-text">
Craik can detect and use a Stigmem node through the minimum v0.1.0
HTTP endpoint surface.
</p>
<p className="craik-product-feature__quote-attribution">— Connecting Stigmem · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/stigmem-docs-demo/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Demo</span>
</div>
<h4 className="craik-adr-card__title">Stigmem docs demo</h4>
<p className="craik-adr-card__decision">
The first runnable demo. Reconciles Stigmem documentation and observed
runtime state without editing files. CI exercises the same command on
every PR — <code>craik demo stigmem-docs --repo-path . --no-github</code>.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/memory-backends/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract</span>
</div>
<h4 className="craik-adr-card__title">Memory backends</h4>
<p className="craik-adr-card__decision">
The proposal-first interface every memory backend implements: create
reviewable proposals, list by task or status, approve or reject with
audit, and refuse direct durable writes without a matching grant.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/stigmem-compatibility/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Compatibility</span>
</div>
<h4 className="craik-adr-card__title">Stigmem compatibility</h4>
<p className="craik-adr-card__decision">
The minimum endpoint matrix for v0.1: health, capability discovery,
fact read, fact provenance. Future endpoints (direct write, federation
hooks) remain explicitly post-MVP.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/local-store/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Persistence</span>
</div>
<h4 className="craik-adr-card__title">Local store</h4>
<p className="craik-adr-card__decision">
SQLite at <code>$CRAIK_HOME/state/craik.sqlite3</code>. Holds projects,
tasks, case files, intent locks, receipts, handoffs, memory proposals,
contradictions, run state, and work-graph projections.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/local-state/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">On-disk layout</span>
</div>
<h4 className="craik-adr-card__title">Local state layout</h4>
<p className="craik-adr-card__decision">
The full <code>~/.craik/</code> directory map: <code>config/</code>,
<code>secrets/</code>, <code>state/</code>, <code>cache/</code>,
<code>logs/</code>, <code>receipts/</code>, <code>handoffs/</code>,
<code>case-files/</code>, <code>projects/</code>.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">06</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">CLI &amp; configuration</p>
<h3 className="craik-section-banner__title">
Flags, env vars, file shapes — <em>the operator surface.</em>
</h3>
<p className="craik-section-banner__lede">
Four docs cover the addressable command surface and how it composes
with configuration: the autogenerated CLI reference, the
<code>CRAIK_HOME</code>-backed configuration model, the read-only
GitHub adapter, and the CI/CD gate matrix that runs on every PR.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/cli/">
<div>
<p className="craik-product-feature__num">Generated · 01</p>
<h4 className="craik-product-feature__title">CLI reference</h4>
<p className="craik-product-feature__summary">
The full <code>craik</code> command surface — autogenerated from the
shipped Typer commands. Lists every command group, the flags it
accepts, and the structured output it produces. Use this as the
authoritative reference for what Craik exposes today.
</p>
<ul className="craik-product-feature__topics">
<li>command groups</li>
<li>flags &amp; options</li>
<li>structured output</li>
<li>autogenerated</li>
</ul>
<span className="craik-product-feature__cta">Read CLI reference</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Authoritative</p>
<p className="craik-product-feature__quote-text">
Craik exposes the <code>craik</code> command. The reference is
generated by <code>scripts/generate_cli_reference.py</code> — never
edited by hand, so the docs match the shipped binary.
</p>
<p className="craik-product-feature__quote-attribution">— CLI reference · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/config/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Config</span>
</div>
<h4 className="craik-adr-card__title">Config reference</h4>
<p className="craik-adr-card__decision">
Craik v0.1 is configured primarily through environment variables and
local state under <code>CRAIK_HOME</code>. The reference enumerates
every recognized variable and its purpose.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/github-config/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Adapter</span>
</div>
<h4 className="craik-adr-card__title">GitHub config</h4>
<p className="craik-adr-card__decision">
The GitHub adapter is read-only in v0.1: issues, PRs, comments,
review state, and CI checks flow in as case-file evidence. Direct
writes are explicitly post-MVP.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/ci-cd/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Gates</span>
</div>
<h4 className="craik-adr-card__title">CI/CD gates</h4>
<p className="craik-adr-card__decision">
Craik CI is split by surface so failures point at the area that
regressed: unit, contract, integration, quickstart smoke, policy
gate, lint, type, security, and CodeQL.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">07</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Side effects, failure &amp; recovery</p>
<h3 className="craik-section-banner__title">
Where Craik draws <em>the line.</em>
</h3>
<p className="craik-section-banner__lede">
Side effects pass through policy, grant, redaction, and receipt
boundaries — never through a raw call. When a run fails, recovery
mode gives the next agent a bounded continuity view before it acts.
Six docs cover the wrappers, the failure posture, recovery,
provenance, the self-audit, and what's explicitly post-MVP.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/side-effect-wrappers/">
<div>
<p className="craik-product-feature__num">Boundary · 01</p>
<h4 className="craik-product-feature__title">Side-effect wrappers</h4>
<p className="craik-product-feature__summary">
<code>craik.runtime.side_effects</code> wraps every effectful
operation — shell command references, repository file writes, durable
memory or Stigmem fact writes — so they cannot bypass policy, grants,
redaction, or receipts. The wrappers are how the MVP keeps the
boundary honest.
</p>
<ul className="craik-product-feature__topics">
<li>shell refs</li>
<li>file writes</li>
<li>memory writes</li>
<li>receipt-bearing</li>
</ul>
<span className="craik-product-feature__cta">Read the wrappers</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Single boundary</p>
<p className="craik-product-feature__quote-text">
Craik side effects must pass through policy, grant, redaction, and
receipt boundaries.
</p>
<p className="craik-product-feature__quote-attribution">— Side-effect wrappers · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/failure-modes/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Posture</span>
</div>
<h4 className="craik-adr-card__title">Failure modes</h4>
<p className="craik-adr-card__decision">
The fail-closed MVP posture. Prompt-injection containment, secret
rejection at persistence, denied-capability handling, fail-open
visibility, automation stops, and the explicit list of paths the MVP
does <em>not</em> claim.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/recovery/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Continuity</span>
</div>
<h4 className="craik-adr-card__title">Recovery mode</h4>
<p className="craik-adr-card__decision">
Bounded continuity view for a resuming agent. Summarizes the latest
handoff, case files, receipts, open contradictions, and active
instruction constraints. It does not resolve contradictions or
replace policy checks.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/public-boundary-provenance/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Provenance</span>
</div>
<h4 className="craik-adr-card__title">Public boundary &amp; provenance</h4>
<p className="craik-adr-card__decision">
Public docs must not expose private paths, raw credentials, or
internal task labels. <code>craik.runtime.projects.public_docs</code>
provides the machine-checkable MVP boundary.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/self-audit/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Honesty</span>
</div>
<h4 className="craik-adr-card__title">Self-audit</h4>
<p className="craik-adr-card__decision">
Every structured handoff includes a <code>self_audit</code> object —
the six honesty checks (schema, redaction, receipts, assumptions,
validation, policy exceptions) that keep incomplete runs from masking
as complete.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/post-mvp-scope/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Post-MVP</span>
</div>
<h4 className="craik-adr-card__title">Post-MVP scope</h4>
<p className="craik-adr-card__decision">
The 0.x MVP is not a 1.0 compatibility promise. Scope explicitly
excludes hosted gateway dispatch, operator dashboards, additional live
runners, marketplace workflows, and visual companion surfaces.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">08</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Skills &amp; plugins</p>
<h3 className="craik-section-banner__title">
Growing the runtime — <em>without giving up governance.</em>
</h3>
<p className="craik-section-banner__lede">
Skills package reusable operating guidance. Plugins package executable
extensions. Both have to compose with policy, grants, receipts,
provenance, and promotion gates so reviewers can audit what changed and
why. Fourteen docs cover the contracts.
</p>
<p className="craik-section-banner__lede">
<strong>Note:</strong> broad marketplace and community-ecosystem
workflows are explicitly <em>post-MVP scope</em>. The MVP ships the
contracts and approval flow; distribution is later.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/community-skills/">
<div>
<p className="craik-product-feature__num">Entry · 01</p>
<h4 className="craik-product-feature__title">Community skills</h4>
<p className="craik-product-feature__summary">
Skills package reusable instructions, examples, and optional assets
for a bounded workflow. They should be easy to inspect before use and
safe to run under Craik policy. The skill flow runs in MVP today;
marketplace distribution is post-MVP.
</p>
<ul className="craik-product-feature__topics">
<li>reusable guidance</li>
<li>inspect before use</li>
<li>policy-safe</li>
<li>post-MVP marketplace</li>
</ul>
<span className="craik-product-feature__cta">Read the guide</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Bounded</p>
<p className="craik-product-feature__quote-text">
Community skills package reusable instructions, examples, and optional
assets for a bounded workflow. They should be easy to inspect before
use and safe to run under Craik policy.
</p>
<p className="craik-product-feature__quote-attribution">— Community skills · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/community-plugins/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guide · plugins</span>
</div>
<h4 className="craik-adr-card__title">Community plugins</h4>
<p className="craik-adr-card__decision">
Plugins package executable extensions. Treat them as untrusted until
their descriptor, provenance, review state, grants, and receipts have
been inspected. Marketplace workflows are post-MVP.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-packages/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill packages</h4>
<p className="craik-adr-card__decision">
<code>craik.skill_package</code> records reusable instructions,
entrypoints, docs, and assets. Packages do not carry plugin runtime
authority — they are pure operating guidance.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-registries/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill registries</h4>
<p className="craik-adr-card__decision">
<code>craik.skill_registry</code> records project-local and global
skill entries and where each came from — so a reviewer can audit
which skills a project can use at a given point in time.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-contexts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill invocation contexts</h4>
<p className="craik-adr-card__decision">
<code>craik.skill_invocation_context</code> links a skill run to its
task, skill package, policy envelope, and optional handoff — the
auditable boundary for one skill invocation.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-telemetry/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill telemetry</h4>
<p className="craik-adr-card__decision">
<code>SkillPerformanceTelemetry</code> records how one invocation
behaved without allowing the agent to silently rewrite reusable
guidance.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-proposals/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">07</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill proposals</h4>
<p className="craik-adr-card__decision">
<code>SkillChangeProposal</code> lets agents draft changes to reusable
operating guidance without silently changing their own authority.
Reviewer approval gates promotion.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-replay/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">08</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill replay</h4>
<p className="craik-adr-card__decision">
<code>SkillReplayFixture</code> compares current skill behavior against
redacted, reproducible fixtures before learning-loop changes are
promoted.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-promotion-gates/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">09</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill promotion gates</h4>
<p className="craik-adr-card__decision">
<code>SkillPromotionRequest</code> prevents reviewed skill proposals
from becoming promoted guidance without explicit approval — every
promotion is named and dated.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/skill-rollbacks/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">10</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · skill</span>
</div>
<h4 className="craik-adr-card__title">Skill rollbacks</h4>
<p className="craik-adr-card__decision">
<code>SkillRollbackTarget</code> provides a reviewable path for
reverting promoted skill updates when a promoted version causes
regressions or violates policy.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/plugin-descriptors/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">11</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · plugin</span>
</div>
<h4 className="craik-adr-card__title">Plugin descriptors</h4>
<p className="craik-adr-card__decision">
<code>craik.plugin_descriptor</code> records governed plugin metadata
without granting runtime authority. Authority comes from grants and
receipts — never the descriptor alone.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/plugin-probation/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">12</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · plugin</span>
</div>
<h4 className="craik-adr-card__title">Plugin probation</h4>
<p className="craik-adr-card__decision">
<code>craik.plugin_probation</code> keeps new or changed plugins out of
durable trust until review criteria are satisfied. Probation is the
gate between "available" and "trusted".
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/plugin-receipts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">13</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · plugin</span>
</div>
<h4 className="craik-adr-card__title">Plugin receipts</h4>
<p className="craik-adr-card__decision">
<code>craik.plugin_receipt</code> records plugin actions and outputs
under policy — joinable to the task, actor, and the plugin descriptor
that authorized the call.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/plugin-capability-grants/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">14</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Contract · plugin</span>
</div>
<h4 className="craik-adr-card__title">Plugin capability grants</h4>
<p className="craik-adr-card__decision">
The grant shape that authorizes a plugin to act under policy. Like
regular capability grants but with plugin-descriptor binding so the
authority can be retracted at the plugin boundary.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

### 9 · Integrations & migrations

GitHub, MCP, adjacent runtimes, and migration paths from existing tools.

- [GitHub adapter](guides/github-adapter.md)
- [MCP ecosystem compatibility](guides/mcp-ecosystem-compatibility.md)
- [MCP client](reference/mcp-client.md)
- [MCP export boundary](reference/mcp-export-boundary.md)
- [Reference integrations](reference/reference-integrations.md)
- [Adjacent runtime bridge](reference/adjacent-runtime-bridge.md)
- [Adjacent tool migration assessment](reference/adjacent-tool-migration.md)
- [Multi-agent workflow bridge](reference/multi-agent-workflow-bridge.md)
- [Multi-agent workflow migration assessment](reference/multi-agent-workflow-migration.md)
- [Import dry-run reports](reference/import-dry-run.md)
- [Migration maps](reference/migration-maps.md)

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">10</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Work-graph export</p>
<h3 className="craik-section-banner__title">
The typed graph — <em>exportable for review and audit.</em>
</h3>
<p className="craik-section-banner__lede">
A single command exports the work graph as deterministic, redacted
JSON or Graphviz DOT. Use it for review, audit, or visualization —
the export is a read-only projection over the runtime objects already
in <code>$CRAIK_HOME/state/</code>.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/graph-export/">
<div>
<p className="craik-product-feature__num">Tool · 01</p>
<h4 className="craik-product-feature__title">Graph export</h4>
<p className="craik-product-feature__summary">
<code>craik graph export</code> serializes the work graph. Filter by
task or project, choose JSON or DOT output, pipe to visualization
tooling, or diff between runs. Output is deterministic — the same
state produces byte-identical exports.
</p>
<ul className="craik-product-feature__topics">
<li>JSON output</li>
<li>Graphviz DOT</li>
<li>deterministic</li>
<li>redacted</li>
</ul>
<span className="craik-product-feature__cta">Export the graph</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">One command</p>
<p className="craik-product-feature__quote-text">
Export the local work graph: <code>craik graph export</code>. Output
is deterministic, redacted, and joinable to every other typed object
in the local store.
</p>
<p className="craik-product-feature__quote-attribution">— Graph export · §Intro</p>
</blockquote>
</a>

</div>

## Where to go next

- **Run, monitor, and maintain** → [Operate](operate.md)
- **Govern execution** → [Secure](secure.md)
- **Understand the model** → [Learn](learn.md)
