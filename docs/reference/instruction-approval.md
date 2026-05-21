# Instruction approval

<p className="craik-meta"><span>5 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The operator review contract for approving or rejecting distilled
instruction proposals, including review receipts, promoted
constraints, and the override path for stale or contradicted items.

</div>

<div className="craik-keypoint">

**Approval is the authority boundary.**

Registration and ingestion discover candidate instructions. Approval
is the first step that can make a distilled instruction govern a case
file, handoff, onboarding context, or compiled prompt.

</div>

## Review commands

```sh
craik instructions list --status proposed
craik instructions show <item-id>
craik instructions approve <item-id> --rationale "Required for release work"
craik instructions reject <item-id> --rationale "Conflicts with project policy"
```

<div className="craik-fields">

<div>
<dt>Command</dt>
<dt><span className="craik-fields__type">Effect</span></dt>
<dd>Receipt behavior</dd>
</div>

<div>
<dt><code>list</code></dt>
<dt><span className="craik-fields__type">read</span></dt>
<dd>Filters proposals by status, source, or category.</dd>
</div>

<div>
<dt><code>show</code></dt>
<dt><span className="craik-fields__type">read</span></dt>
<dd>Displays statement, category, source, provenance, freshness, and contradiction state.</dd>
</div>

<div>
<dt><code>approve</code></dt>
<dt><span className="craik-fields__type">write</span></dt>
<dd>Creates an approval review and active promoted constraint.</dd>
</div>

<div>
<dt><code>reject</code></dt>
<dt><span className="craik-fields__type">write</span></dt>
<dd>Creates a denial review and leaves no active constraint.</dd>
</div>

</div>

Review commands run through the active operator session. The runtime
records who made the decision, when it happened, the rationale, and
the proposal state at review time.

Direct runtime API calls also require an active operator session by
default. Test harnesses or tightly controlled internal tooling may opt
into unbound approval by passing `allow_unbound=True`; production
extensions should leave the default in place so the recorded operator
identity is bound to the current session.

## Receipts

`craik.instruction_promotion_review` links the decision to the
proposal, policy envelope, receipt chain, handoffs, and active
constraint when one is created.

<div className="craik-grid">

<div><h4>Approve</h4><p>Moves a fresh proposal to <code>governing</code> and creates a <code>craik.promoted_instruction_constraint</code>.</p></div>
<div><h4>Reject</h4><p>Records a denial and keeps the proposal out of active runtime context.</p></div>
<div><h4>Repeat approve</h4><p>Returns the existing review and constraint instead of duplicating authority.</p></div>
<div><h4>Deferred approve</h4><p>Requires an explicit override when the item is stale or contradicted.</p></div>

</div>

Active constraints retain proposal ID, source ID, source snapshot ID,
provenance IDs, evidence IDs, review links, and a receipt HMAC.
Downstream consumers must read governing constraints from the approval
API instead of raw proposal rows. Reviews with missing or invalid
receipt HMACs are treated as needing re-approval and are excluded from
active runtime context.

## Overrides

Stale or contradicted proposals are blocked from normal approval. An
operator can approve one only by setting `--override` and providing
`--override-rationale`.

```sh
craik instructions approve <item-id> \
  --override \
  --override-rationale "Accepted while policy document migration is in progress"
```

<div className="craik-keypoint">

**Override rationale is mandatory.**

The review records whether a stale guard or contradiction guard was
bypassed. Missing rationale fails before the proposal becomes
governing, and the resulting review is integrity-protected before it
is stored.

</div>

Informational override rationale can also be recorded for non-stale,
non-contradicted approvals. In that case the review stores the
rationale while keeping the stale and contradiction override flags
false.

## Runtime consumers

Approved constraints flow into:

<div className="craik-grid">

<div><h4>Case files</h4><p>The <code>distillations</code> evidence section.</p></div>
<div><h4>Compiled prompts</h4><p>The <code>Active instruction constraints</code> section.</p></div>
<div><h4>Onboarding</h4><p>Active project constraints and stale warnings.</p></div>
<div><h4>Handoffs</h4><p>Constraint IDs carried forward for audit.</p></div>

</div>

If a source later changes or disappears, stale invalidation defers the
affected proposals and excludes them from active runtime context until
they are reviewed again.

## What's next

<div className="craik-next">

<a href="../distilled-instructions/">
<strong>Reference</strong>
<span>Distilled instructions</span>
<small>Lifecycle states, categories, provenance, and snapshot linkage.</small>
</a>

<a href="../prompt-compiler/">
<strong>Reference</strong>
<span>Prompt compiler</span>
<small>How approved constraints appear in runner-ready prompts.</small>
</a>

<a href="../../guides/managing-instructions/">
<strong>Guide</strong>
<span>Managing instructions</span>
<small>The end-to-end operator workflow.</small>
</a>

</div>
