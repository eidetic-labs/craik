# Memory impact preview view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator display for proposed memory writes before
promotion or direct write attempts — preview risks, evidence gaps,
and the boundary that keeps proposals visually separate from facts
through `craik operator memory-impact`.

</div>

<div className="craik-keypoint">

**Proposals are not accepted facts.**

The view lists proposals separately from <code>facts_to_add</code>
and <code>facts_to_invalidate</code> so operators can see the
proposed change without treating it as durable memory.

</div>

## Commands

```bash
craik operator memory-impact PREVIEW_ID
craik operator memory-impact PREVIEW_ID --json
```

`craik operator memory-impact` prints one persisted memory impact
preview by ID. The JSON form emits the same read-only snapshot with
the preview, task-scoped proposals, optional policy envelope ID, and
receipt IDs for downstream tooling.

## What it formats

<div className="craik-grid">

<div><h4>Pending memory proposals</h4><p>And status.</p></div>
<div><h4>Facts to add or update</h4></div>
<div><h4>Facts to invalidate</h4></div>
<div><h4>Proposals missing evidence</h4></div>
<div><h4>Likely contradiction risks</h4></div>
<div><h4>Scope counts</h4></div>
<div><h4>Policy envelope &amp; receipt links</h4><p>When available.</p></div>

</div>

## Preview boundary

Pending and rejected proposals remain review records. Approved
proposals still require the configured backend and policy path before
becoming durable facts.

## Evidence and contradictions

<div className="craik-keypoint">

**Likely contradictions are preview risks, not resolved conflicts.**

A contradiction preview points to the existing value, proposed value,
and reason so the operator can decide whether to approve, reject,
revise, or open a formal contradiction review.

</div>

Evidence gaps are shown by proposal ID.

## What's next

<div className="craik-next">

<a href="../memory-backends/">
<strong>Reference</strong>
<span>Memory backends</span>
<small>The backends that consume promoted proposals.</small>
</a>

<a href="../../guides/memory-proposals/">
<strong>Guide</strong>
<span>Memory proposals</span>
<small>The operator workflow this view supports.</small>
</a>

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

</div>
