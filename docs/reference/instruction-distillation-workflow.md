# Runtime instruction distillation workflow

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The 9-step pipeline that turns declared instruction files into
reviewed, provenance-linked runtime constraints — and the operator
rules that keep raw files from becoming automatic authority.

</div>

<div className="craik-keypoint">

**Raw instruction files are evidence, not authority.**

Every step preserves provenance and keeps proposals inactive until a
human approves them.

</div>

## Workflow

<ol className="craik-steps">
<li>Register declared sources with <code>craik.instruction_source_registry</code>.</li>
<li>Capture source identity with <code>craik.instruction_source_snapshot</code>.</li>
<li>Link extracted text with <code>craik.instruction_provenance</code>.</li>
<li>Create reviewable <code>craik.distilled_instruction_proposal</code> records.</li>
<li>Invalidate proposals when source snapshots change, go missing, are new, or are omitted from the current scan.</li>
<li>Open <code>craik.contradiction_report</code> records when authoritative instruction proposals conflict across sources.</li>
<li>Record <code>craik.instruction_promotion_review</code> decisions.</li>
<li>Create <code>craik.promoted_instruction_constraint</code> only for approved proposals.</li>
<li>Consume active constraints in case files, prompts, onboarding, and handoffs.</li>
</ol>

## Operator rules

<div className="craik-grid">

<div><h4>Inactive until approved</h4><p>Proposed distillations are inactive until approved.</p></div>
<div><h4>Visible but inactive</h4><p>Stale, contradicted, rejected, and deferred distillations remain visible but inactive.</p></div>
<div><h4>Override required</h4><p>Approving stale or contradicted proposals requires an explicit override rationale on the promotion review.</p></div>
<div><h4>Audit trail required</h4><p>Active constraints retain source ID, source snapshot ID, provenance IDs, evidence IDs, and review links.</p></div>
<div><h4>Stale-risk warnings</h4><p>Case files and onboarding surface stale-risk warnings instead of treating stale distillations as facts.</p></div>
<div><h4>CLI lifecycle</h4><p><code>craik instructions</code> registers sources, lists proposals, records approval decisions, and shows provenance through the active operator session.</p></div>
<div><h4>Forward to next agent</h4><p>Handoffs carry active instruction constraint IDs forward so later agents can audit what shaped the run.</p></div>

</div>

## Fixtures

The contract fixture file includes examples for the core v0.4.0
records.

<div className="craik-grid">

<div><h4><code>craik.instruction_source</code></h4></div>
<div><h4><code>craik.instruction_source_registry</code></h4></div>
<div><h4><code>craik.instruction_source_snapshot</code></h4></div>
<div><h4><code>craik.instruction_provenance</code></h4></div>
<div><h4><code>craik.distilled_instruction_proposal</code></h4></div>
<div><h4><code>craik.instruction_promotion_review</code></h4></div>
<div><h4><code>craik.promoted_instruction_constraint</code></h4></div>

</div>

Runtime tests cover stale invalidation, contradiction handling,
promotion review, and active-context consumption.

## What's next

<div className="craik-next">

<a href="../instruction-sources/">
<strong>Reference</strong>
<span>Instruction sources</span>
<small>Registry boundaries, categories, and stale invalidation.</small>
</a>

<a href="../instruction-distillation-view/">
<strong>Reference</strong>
<span>Instruction distillation view</span>
<small>The operator surface that audits proposals.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>All instruction-related contract shapes.</small>
</a>

</div>
