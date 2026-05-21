# Known traps and negative knowledge

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

Two related contracts agents use to avoid repeating known mistakes:
`craik.known_trap` (evidence-backed pitfalls) and
`craik.negative_knowledge` (evidence-backed statements about what is
not true or not available in a scope).

</div>

<div className="craik-keypoint">

**Absence needs evidence too.**

Use negative knowledge only when absence matters and there is evidence
for it — inspected repository tree, fresh tool attestation, etc. Don't
promote unsupported guesses about absence into negative knowledge.

</div>

## Contracts

<div className="craik-fields">

<div>
<dt>Contract</dt>
<dt><span className="craik-fields__type">Records</span></dt>
<dd>Lifecycle</dd>
</div>

<div>
<dt><code>craik.known_trap</code></dt>
<dt><span className="craik-fields__type">pitfall</span></dt>
<dd>Trap statement · avoidance guidance · evidence · handoff links · optional expiry · whether the trap is active, expired, or contradicted.</dd>
</div>

<div>
<dt><code>craik.negative_knowledge</code></dt>
<dt><span className="craik-fields__type">absence</span></dt>
<dd>Bounded negative statement · scope · trust class · evidence · handoff links · contradictions · optional expiry.</dd>
</div>

</div>

<div className="craik-keypoint">

**Active, unexpired traps and negative knowledge are surfaced.**

Onboarding and case-file stale-risk warnings include active known traps
and active negative knowledge so agents can avoid repeating known
mistakes or relying on disproven availability claims.

</div>

## Capture commands

<div className="craik-fields">

<div>
<dt>Command</dt>
<dt><span className="craik-fields__type">Writes</span></dt>
<dd>Boundary</dd>
</div>

<div>
<dt><code>craik knowledge trap</code></dt>
<dt><span className="craik-fields__type">known trap</span></dt>
<dd>Requires an active operator session and evidence ids. The record guides future agents but does not grant policy authority.</dd>
</div>

<div>
<dt><code>craik knowledge negative</code></dt>
<dt><span className="craik-fields__type">negative knowledge</span></dt>
<dd>Requires evidence and scope. If a positive assertion is supplied as contradicted, Craik opens a contradiction instead of silently replacing it.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../known-traps-view/">
<strong>Reference</strong>
<span>Known traps view</span>
<small>The operator surface formatter for traps.</small>
</a>

<a href="../freshness/">
<strong>Reference</strong>
<span>Freshness</span>
<small>How knowledge expiry interacts with stale-risk warnings.</small>
</a>

<a href="../../guides/agent-onboarding/">
<strong>Guide</strong>
<span>Agent onboarding</span>
<small>The first surface that exposes active traps.</small>
</a>

</div>
