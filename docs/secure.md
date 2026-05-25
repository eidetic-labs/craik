---
id: secure
title: Secure
sidebar_label: Overview
sidebar_position: 0
description: Govern execution, manage identity and credentials, control side effects, and keep durable audit trails.
slug: /secure
---

# Secure Craik

Craik treats governance as a runtime concern. Policy envelopes, capability
grants, credential identity, redaction, and sandboxes are all addressable
objects — not advisory configuration. This section is the implementation map
for everyone responsible for the safety, identity, and audit properties of
their Craik install.

## Implementation paths

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">01</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Governance fundamentals</p>
<h3 className="craik-section-banner__title">
Policy is <em>part of the runtime contract.</em>
</h3>
<p className="craik-section-banner__lede">
Start here to understand what "governance" means inside the runtime,
then configure the basic envelope you want every task to run inside.
Five docs cover the concept, the runtime model, the grant surface,
the scope-control flow, and the narrow fail-open exception.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../concepts/governance/">
<div>
<p className="craik-product-feature__num">Concept · 01</p>
<h4 className="craik-product-feature__title">Governance</h4>
<p className="craik-product-feature__summary">
The governance surface Craik enforces — policy profiles, capability
grants, immutable paths, fail-open visibility, receipts, redaction,
memory-proposal defaults, and the policy regression gate. Strict by
default; trusted-local is opt-in; automation is fail-closed.
</p>
<ul className="craik-product-feature__topics">
<li>policy profiles</li>
<li>capability grants</li>
<li>immutable paths</li>
<li>release gate</li>
</ul>
<span className="craik-product-feature__cta">Read the concept</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Runtime-native</p>
<p className="craik-product-feature__quote-text">
Craik should be governance-native. Policy is not an enterprise add-on;
it is part of the runtime contract.
</p>
<p className="craik-product-feature__quote-attribution">— Governance model · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../governance/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Model</span>
</div>
<h4 className="craik-adr-card__title">Governance model</h4>
<p className="craik-adr-card__decision">
The top-level statement of intent: Craik must be governance-native,
not an enterprise add-on. Policy travels with every run, every grant
is typed, every immutable boundary is enforced.
</p>
<span className="craik-adr-card__cta">Read</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/capability-grants/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Grants</span>
</div>
<h4 className="craik-adr-card__title">Capability grants</h4>
<p className="craik-adr-card__decision">
Side effects require explicit, scoped grants — no ambient authority.
Three practical outcomes: allowed, denied, or requires_approval. The
v0.1 runtime enforces four capability hooks today.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/scope-control/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Scope</span>
</div>
<h4 className="craik-adr-card__title">Scope control</h4>
<p className="craik-adr-card__decision">
The six intent-lock knobs (<code>accepted_interpretation</code>,
<code>in-scope</code>, <code>out-of-scope</code>, allowed autonomy,
stop conditions, scope-change rules) plus the mid-run update flow.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/fail-open/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Exception</span>
</div>
<h4 className="craik-adr-card__title">Fail-open behavior</h4>
<p className="craik-adr-card__decision">
Default is fail-closed. Fail-open is profile-gated, opt-in only, and
never bypasses redaction, receipts, immutable paths, or memory-write
approvals. Automation is always fail-closed.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">02</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Policy</p>
<h3 className="craik-section-banner__title">
The policy envelope — <em>per-run governance object.</em>
</h3>
<p className="craik-section-banner__lede">
Three docs cover the policy contract: the named profiles Craik ships,
the regression-test harness that verifies the profile contract, and
the operator workflow for running it locally and in CI.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/policy-profiles/">
<div>
<p className="craik-product-feature__num">Profiles · 01</p>
<h4 className="craik-product-feature__title">Policy profiles</h4>
<p className="craik-product-feature__summary">
The named profiles Craik ships — <code>strict</code> (default),
<code>trusted-local</code> (opt-in fail-open), and <code>automation</code>
(strict-but-headless). Design rationale lives in
<a href="../adr/policy-envelope-shape/">ADR 0004</a>.
</p>
<ul className="craik-product-feature__topics">
<li>strict default</li>
<li>trusted-local</li>
<li>automation</li>
<li>ADR 0004</li>
</ul>
<span className="craik-product-feature__cta">Read profiles</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Design rationale</p>
<p className="craik-product-feature__quote-text">
Design rationale: ADR 0004 Policy Envelope Shape — actor, task,
profile, grant requirements, redaction posture, and receipt
obligations all bound into one typed record.
</p>
<p className="craik-product-feature__quote-attribution">— Policy profiles · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/policy-tests/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Gate</span>
</div>
<h4 className="craik-adr-card__title">Policy tests</h4>
<p className="craik-adr-card__decision">
<code>craik policy test</code> is the machine-readable policy
regression gate for v0.1. Exits non-zero on any violated check and
prints a structured <code>craik.policy_test_report</code>.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/running-policy-tests/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Operator</span>
</div>
<h4 className="craik-adr-card__title">Running policy tests</h4>
<p className="craik-adr-card__decision">
How operators and release engineers run the policy gate locally
and in CI — what each of the six checks covers, how to extend the
suite, and where the harness touches local state.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">03</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Identity &amp; credentials</p>
<h3 className="craik-section-banner__title">
Operator identity — <em>separate from credential identity.</em>
</h3>
<p className="craik-section-banner__lede">
Every provider call is bound to both an OIDC operator identity and a
typed credential profile. Receipts record both, so audit can answer
both "who authorized this" and "which credential carried it" without
inspecting secret material. Two docs cover the working surface and the
underlying design.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/authentication/">
<div>
<p className="craik-product-feature__num">Workflow · 01</p>
<h4 className="craik-product-feature__title">Authentication &amp; credentials</h4>
<p className="craik-product-feature__summary">
The operator-facing surface: OIDC login, credential profiles (api-key,
provider OAuth, keyring-ref, vendor-cli), credential pools with rotation and failover,
workload identity for CI, and the approval-gated first-use flow. Every
credential is referenced — never copied.
</p>
<ul className="craik-product-feature__topics">
<li>OIDC operator identity</li>
<li>typed credential profiles</li>
<li>credential pools</li>
<li>workload identity</li>
</ul>
<span className="craik-product-feature__cta">Walk the auth flow</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Two identities</p>
<p className="craik-product-feature__quote-text">
Craik separates operator identity from credential identity. The
operator is the human or automation identity driving a run. The
credential is the provider account used for model calls. Provider
receipts record both.
</p>
<p className="craik-product-feature__quote-attribution">— Authentication · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../adr/credential-and-identity-architecture/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">ADR 0007</span>
<span className="craik-adr-card__status">Accepted</span>
</div>
<h4 className="craik-adr-card__title">Credential &amp; identity architecture</h4>
<p className="craik-adr-card__decision">
The design rationale. Credentials and operator identity are
governance inputs — never incidental plumbing. Every receipt names
which human authorized work, which credential carried the call,
which policy allowed it, and which grant made the credential usable.
</p>
<span className="craik-adr-card__cta">Read decision</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">04</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Secrets, redaction &amp; release</p>
<h3 className="craik-section-banner__title">
Secrets travel as <em>references — never values.</em>
</h3>
<p className="craik-section-banner__lede">
Four docs cover the secret lifecycle: where secret material lives,
the central redaction utility that scrubs every persistence boundary,
the migration policy that refuses to copy secrets across runtime
boundaries, and the release process that preserves these properties
across version bumps.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../security/secrets/">
<div>
<p className="craik-product-feature__num">Overview · 01</p>
<h4 className="craik-product-feature__title">Secrets</h4>
<p className="craik-product-feature__summary">
Where secret material lives, the owner-only-permissions discipline,
what the redaction guard never lets through to receipts / handoffs /
logs / case files / memory proposals, why policy and grants don't
override redaction, and how to extend the guard for project-specific
patterns.
</p>
<ul className="craik-product-feature__topics">
<li>secrets directory</li>
<li>five redaction categories</li>
<li>policy + grants don't override</li>
<li>extensibility</li>
</ul>
<span className="craik-product-feature__cta">Read the overview</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Tier</p>
<p className="craik-product-feature__quote-text">
Craik treats secrets as sensitive runtime material — not as
configuration. They live in a single, narrow directory; they never
leak into receipts, case files, or handoffs in raw form.
</p>
<p className="craik-product-feature__quote-attribution">— Secrets · §Key-point</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/redaction/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Guard</span>
</div>
<h4 className="craik-adr-card__title">Redaction</h4>
<p className="craik-adr-card__decision">
The central runtime redaction utility runs before every persistence
boundary. Bearer tokens, key/value secret shapes, auth URLs,
configured patterns, and structured fields with secret-like names —
all scrubbed before storage.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/secret-migration-policy/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Policy</span>
</div>
<h4 className="craik-adr-card__title">Secret migration policy</h4>
<p className="craik-adr-card__decision">
Migrations must never copy secret values across runtime boundaries.
Four policy outcomes: <code>redact</code> · <code>strip</code> ·
<code>reference</code> · <code>reject</code> — never copy as-is.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../security/release-process/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Process</span>
</div>
<h4 className="craik-adr-card__title">Security release process</h4>
<p className="craik-adr-card__decision">
Security releases use the same package gates as normal releases, plus
additional advisory and disclosure handling — so security fixes never
skip the regression suite or the doc-update obligation.
</p>
<span className="craik-adr-card__cta">Process</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">05</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Evidence &amp; memory governance</p>
<h3 className="craik-section-banner__title">
Memory is governed — <em>truth doesn't silently overwrite truth.</em>
</h3>
<p className="craik-section-banner__lede">
Five docs cover how Craik separates evidence from assumptions, how
contradictions surface and resolve, and how every memory update
flows through proposals, diffs, and impact previews before it can
become a durable fact.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../guides/evidence-and-assumptions/">
<div>
<p className="craik-product-feature__num">Foundation · 01</p>
<h4 className="craik-product-feature__title">Evidence &amp; assumptions</h4>
<p className="craik-product-feature__summary">
The honesty rule that grounds memory governance. Evidence is source
material the runtime can cite. Assumptions are unresolved claims that
should not be treated as facts yet. Promotion requires evidence —
period.
</p>
<ul className="craik-product-feature__topics">
<li>evidence_reference fields</li>
<li>assumption ledger</li>
<li>promotion rule</li>
<li>immutable docs as evidence</li>
</ul>
<span className="craik-product-feature__cta">Read the foundation</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Honesty rule</p>
<p className="craik-product-feature__quote-text">
Evidence is source material the runtime can cite. Assumptions are
unresolved claims that should not be treated as facts yet. Conflating
the two is how an agent runtime starts hallucinating policy.
</p>
<p className="craik-product-feature__quote-attribution">— Evidence &amp; assumptions · §Key-point</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../guides/contradiction-inbox/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Inbox</span>
</div>
<h4 className="craik-adr-card__title">Contradiction inbox</h4>
<p className="craik-adr-card__decision">
First-class workflow record for "two things disagree" — docs vs.
implementation, handoff vs. branch state, reviewer vs. implementer.
Distinct from Stigmem memory-substrate conflicts; cross-linkable when
both exist.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/memory-proposals/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Lifecycle</span>
</div>
<h4 className="craik-adr-card__title">Memory proposals</h4>
<p className="craik-adr-card__decision">
Create, list, approve, reject — and the promotion rule that requires
evidence. Direct durable writes still need a
<code>memory.write</code> grant; until then, proposals are the path.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/memory-diffs/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Audit</span>
</div>
<h4 className="craik-adr-card__title">Memory diffs</h4>
<p className="craik-adr-card__decision">
What a task changed in memory: proposals created, approved, rejected;
facts written and read; write failures. The single object reviewers
inspect when deciding whether a run's memory effect was acceptable.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../guides/memory-impact-preview/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Preview</span>
</div>
<h4 className="craik-adr-card__title">Memory impact preview</h4>
<p className="craik-adr-card__decision">
The read-only forecast before promotion: facts that would be added or
invalidated, likely contradictions, proposals missing evidence, and
scope visibility counts. Previews never write.
</p>
<span className="craik-adr-card__cta">Guide</span>
</a>
</li>

</ol>

<header className="craik-section-banner">
<div className="craik-section-banner__num" aria-hidden="true">06</div>
<div className="craik-section-banner__body">
<p className="craik-section-banner__kicker">Sandboxing</p>
<h3 className="craik-section-banner__title">
Tool execution under <em>policy-bound sandboxes.</em>
</h3>
<p className="craik-section-banner__lede">
Side effects run inside a sandbox backend chosen to match your trust
boundary. Six docs cover the sandbox contract, the four backends Craik
records (local process, remote shell, Docker, browser), and the
environment receipts every sandbox decision emits.
</p>
</div>
</header>

<div className="craik-product-spread">

<a className="craik-product-feature" href="../reference/sandbox-backends/">
<div>
<p className="craik-product-feature__num">Contract · 01</p>
<h4 className="craik-product-feature__title">Sandbox backends</h4>
<p className="craik-product-feature__summary">
<code>craik.sandbox_backend</code> describes an execution environment
backend without binding it to any model provider. The backend names
its identity, capability requirements, redaction posture, and the
receipts it emits — runners pick a backend by name, not by ambient
process state.
</p>
<ul className="craik-product-feature__topics">
<li>provider-agnostic</li>
<li>capability requirements</li>
<li>receipt boundary</li>
<li>four backends today</li>
</ul>
<span className="craik-product-feature__cta">Read the contract</span>
</div>
<blockquote className="craik-product-feature__quote">
<p className="craik-product-feature__quote-eyebrow">Decision boundary</p>
<p className="craik-product-feature__quote-text">
<code>craik.sandbox_backend</code> describes an execution environment
backend without binding it to any model provider.
</p>
<p className="craik-product-feature__quote-attribution">— Sandbox backends · §Intro</p>
</blockquote>
</a>

</div>

<ol className="craik-adr-grid">

<li>
<a className="craik-adr-card" href="../reference/local-process-backend/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">02</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Backend · local</span>
</div>
<h4 className="craik-adr-card__title">Local process backend</h4>
<p className="craik-adr-card__decision">
Execution through the host process environment. Intentionally a
decision boundary — not ambient shell. Local backend doesn't grant
runtime authority unless a matching grant exists.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/remote-shell-backend/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">03</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Backend · remote</span>
</div>
<h4 className="craik-adr-card__title">Remote shell backend</h4>
<p className="craik-adr-card__decision">
SSH or equivalent remote command execution as an auditable boundary.
The backend records the decision; it does not open connections or
execute commands by itself.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/docker-sandbox-backend/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">04</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Backend · docker</span>
</div>
<h4 className="craik-adr-card__title">Docker sandbox backend</h4>
<p className="craik-adr-card__decision">
Containerized execution as an explicit environment boundary. The
backend records image, build args, and grant boundaries — it doesn't
start containers itself.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/browser-tool-boundary/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">05</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Backend · browser</span>
</div>
<h4 className="craik-adr-card__title">Browser tool boundary</h4>
<p className="craik-adr-card__decision">
Browser automation and tool execution as a policy-controlled sandbox.
The boundary captures origin, profile, allowed surfaces, and the
receipts emitted for each navigation or action.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

<li>
<a className="craik-adr-card" href="../reference/environment-receipts/">
<div className="craik-adr-card__head">
<span className="craik-adr-card__num">06</span>
<span className="craik-adr-card__status craik-adr-card__status--type">Receipt</span>
</div>
<h4 className="craik-adr-card__title">Environment receipts</h4>
<p className="craik-adr-card__decision">
Normal <code>craik.capability_receipt</code> records for provider,
MCP, sandbox, local process, remote shell, browser, and container
decisions. One receipt shape across every environment surface.
</p>
<span className="craik-adr-card__cta">Reference</span>
</a>
</li>

</ol>

## Where to go next

- **Build something new** → [Build](build.md)
- **Run and inspect the system** → [Operate](operate.md)
- **Understand the model** → [Learn](learn.md)
