# Limitations

<p className="craik-meta"><span>4 min read</span><span>For everyone</span><span>Updated 2026-05-20</span></p>

<div className="craik-lead">

**What's in this doc**

The honest scope boundary for the `0.2.0` MVP release line. What's
end-to-end production-ready today, what exists as contract/helper
scaffolding, what's deliberately deferred, and how the v0.x release
posture is framed.

</div>

<div className="craik-keypoint">

**End-to-end versus contract.**

The repository has broad contract, helper, CLI, and documentation
coverage through the v0.12 roadmap — but several surfaces are not yet
end-to-end production workflows. This doc draws the line.

</div>

## Current end-to-end surfaces

The pieces below ship as user-facing workflows with persistence, docs,
tests, and CI coverage.

<div className="craik-grid">

<div><h4>Local home &amp; store</h4><p>Initialization, layout, override via <code>CRAIK_HOME</code>.</p></div>
<div><h4>Project registration</h4><p>Add, list, inspect projects. Task creation.</p></div>
<div><h4>Case-file assembly</h4><p>From local repo state plus optional read-only GitHub context.</p></div>
<div><h4>Local artifacts</h4><p>Receipts, handoffs, memory proposals, contradictions, work-graph inspection.</p></div>
<div><h4>Policy</h4><p>Profile generation, capability-grant checks, regression tests.</p></div>
<div><h4>Stigmem reads</h4><p>Compatibility detection and policy-gated direct fact write helpers.</p></div>
<div><h4>Fixture loop</h4><p>Deterministic fixture loop and runner preview contracts.</p></div>
<div><h4>Provider paths</h4><p>Fixture-backed and live opt-in OpenAI Responses, Anthropic Messages, and OAI-compatible Chat Completions.</p></div>
<div><h4>OIDC login</h4><p>Device-code and loopback+PKCE flows.</p></div>
<div><h4>Credential sources</h4><p>Env-var API keys, local-CLI OAuth fallback, vendor-CLI bridges, secret references, markers, Stigmem-backed references.</p></div>
<div><h4>Credential pools</h4><p>Failover and per-profile health tracking.</p></div>
<div><h4>Identity on receipts</h4><p>Operator and credential identity on every provider receipt.</p></div>
<div><h4>Policy-bound credentials</h4><p>Operators and credentials constrained by policy.</p></div>
<div><h4>Approval-gated first use</h4><p>First live use of a credential requires explicit approval.</p></div>
<div><h4>Resumable runs</h4><p>Provider-backed runs persist phase outputs and idempotency keys so interrupted runs can resume from durable boundaries.</p></div>
<div><h4>Budget enforcement</h4><p>Wall-clock, provider-token, and pre-dispatch time checks interrupt exhausted runs before additional calls or side effects.</p></div>
<div><h4>Local-process sandbox</h4><p>Registered shell command references can execute through the local-process sandbox backend with cancellation propagation.</p></div>
<div><h4>Run recovery views</h4><p><code>craik run show</code>, <code>craik run resume</code>, <code>craik run cancel</code>, and <code>craik run delta</code> expose continuity state.</p></div>
<div><h4>Store migrations</h4><p>Local-store schema changes run through a registered, forward-only migration framework.</p></div>
<div><h4>Stigmem docs demo</h4><p>The accepted release-acceptance workflow.</p></div>

</div>

## Contract or helper surfaces

These surfaces ship as typed contracts, evaluators, formatters, or
fixtures — useful, but **not yet operational workflows**.

<div className="craik-fields">

<div>
<dt>Surface</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>What's missing</dd>
</div>

<div>
<dt>Live provider execution</dt>
<dt><span className="craik-fields__type">opt-in only</span></dt>
<dd>Fixture-backed by default. Live HTTP requires <code>live_enabled=true</code> on <code>ProviderRuntimeConfig</code> plus a resolved credential. CI does not exercise paid live providers.</dd>
</div>

<div>
<dt>Runner adapters</dt>
<dt><span className="craik-fields__type">preview</span></dt>
<dd>Outside governed provider-backed paths, runner adapters remain preview, fixture, or prompt-handoff oriented.</dd>
</div>

<div>
<dt>Execution backends</dt>
<dt><span className="craik-fields__type">partial</span></dt>
<dd>Registered shell command references can execute through the local-process sandbox backend. Docker, remote-shell, browser, and MCP execution backends remain contracts or future surfaces.</dd>
</div>

<div>
<dt>Gateway / channels</dt>
<dt><span className="craik-fields__type">contracts only</span></dt>
<dd>Gateway, webhook, messaging, channel, and scheduled-automation surfaces ship contracts and helpers. No production daemon or dispatch loop yet.</dd>
</div>

<div>
<dt>Operator UI</dt>
<dt><span className="craik-fields__type">view-contract</span></dt>
<dd>Formatter and view-contract level. A full TUI or dashboard is post-MVP unless explicitly pulled into the proof workflow.</dd>
</div>

<div>
<dt>Companion surfaces</dt>
<dt><span className="craik-fields__type">decisions</span></dt>
<dd>Companion, mobile, visual, and multimodal surfaces ship as posture decisions and adapter contracts — not shipped product applications.</dd>
</div>

<div>
<dt>Marketplace</dt>
<dt><span className="craik-fields__type">docs-only</span></dt>
<dd>Marketplace and broad community-ecosystem docs describe future contribution mechanics — not MVP operational support.</dd>
</div>

</div>

## Known MVP gaps

Scheduled milestones with explicit version targets.

<div className="craik-fields">

<div>
<dt>Gap</dt>
<dt><span className="craik-fields__type">Target</span></dt>
<dd>Why it's deferred</dd>
</div>

<div>
<dt>Multi-agent runtime</dt>
<dt><span className="craik-fields__type">v0.3.0</span></dt>
<dd>Handoff consumption, role-based provider dispatch, receipt-backed mailbox messages, intent-lock coordination, structured debate resolution, cross-agent review requests/results, human delegation pause/resume, scope-change interruption/decision records, live work-graph coordination events, and per-agent identity isolation for consumed handoffs are available as first slices.</dd>
</div>

<div>
<dt>Multi-agent prompt injection</dt>
<dt><span className="craik-fields__type">v0.3.0</span></dt>
<dd>Mailbox bodies, debate turns, review findings, scope-change reasons, and handoff next steps or risks are peer-agent content. Craik stores and receipts them, but downstream prompts must treat them as untrusted input rather than privileged instructions.</dd>
</div>

<div>
<dt>Runtime instruction distillation</dt>
<dt><span className="craik-fields__type">v0.4.0</span></dt>
<dd>Pipeline that promotes declared instruction files to runtime proposals.</dd>
</div>

<div>
<dt>Operator UI / TUI</dt>
<dt><span className="craik-fields__type">v0.7.0</span></dt>
<dd>Operator surfaces ship as view contracts in MVP.</dd>
</div>

<div>
<dt>Always-on gateway daemon</dt>
<dt><span className="craik-fields__type">v0.8.0</span></dt>
<dd>Channels and webhook contracts ship in MVP; live daemon waits.</dd>
</div>

<div>
<dt>MCP client/server</dt>
<dt><span className="craik-fields__type">v0.9.0</span></dt>
<dd>Boundary and metadata contracts ship in MVP; live MCP execution waits.</dd>
</div>

</div>

**Other near-term deferrals:** remote Stigmem write promotion after
proposal review · god-file cleanup and runtime sub-packaging before
the MVP freeze · ADR-backed design decisions for runner scope, release
posture, and package boundaries · nightly reliability and artifact
depth beyond the current PR gates · full post-MVP surfaces tracked in
[Post-MVP Scope](reference/post-mvp-scope.md).

## Write authority

<div className="craik-keypoint">

**No ambient write authority.**

Direct durable memory writes, GitHub writes, shell commands, file
writes, and external side effects must be policy-gated, redacted, and
receipt-backed before they are considered MVP-ready. Local memory
proposals remain the default unprivileged path.

</div>

## Release posture

The first release line is `0.x`. Each release is honest about limits
and strong enough for a credible MVP slice — but it is not a `1.0.0`
stability guarantee.

Package version `0.2.0` marks the **durable execution continuity**
gate after the first governed agent-runtime substrate. Roadmap
milestones such as v0.12 remain implementation gates rather than
published-package compatibility guarantees.

## What's next

<div className="craik-next">

<a href="../reference/post-mvp-scope/">
<strong>Reference</strong>
<span>Post-MVP scope</span>
<small>The full list of surfaces deliberately outside MVP, with the gates that move them forward.</small>
</a>

<a href="../mvp-roadmap/">
<strong>Read</strong>
<span>MVP roadmap</span>
<small>The release-readiness checklist driving v0.x.</small>
</a>

<a href="../roadmap/">
<strong>Read</strong>
<span>Roadmap</span>
<small>The broader trajectory through v0.12 and beyond.</small>
</a>

</div>
