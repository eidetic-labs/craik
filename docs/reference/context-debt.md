# Context debt

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The `craik.context_debt_record` contract — how Craik makes known gaps
in the context an agent used explicit, so future agents can decide
whether to continue, refresh, or stop for more information.

</div>

<div className="craik-keypoint">

**Make omissions explicit.**

The structured records are persisted separately so callers can track
owner, source links, next action, carry-forward state, and resolution.

</div>

## What records can represent

<div className="craik-grid">

<div><h4>Omitted documentation</h4></div>
<div><h4>Excluded docs</h4><p>By discovery rules.</p></div>
<div><h4>Stale instruction constraints</h4></div>
<div><h4>Unresolved assumptions</h4></div>
<div><h4>Missing external state</h4><p>Such as GitHub.</p></div>
<div><h4>Missing memory facts</h4></div>
<div><h4>Active instruction constraints carried forward</h4></div>
<div><h4>Missing case files</h4></div>
<div><h4>Other explicit context gaps</h4></div>

</div>

## Lifecycle rules

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Required field</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Open or carried-forward</dt>
<dt><span className="craik-fields__type"><code>next_action</code></span></dt>
<dd>Must be set so the resuming agent knows what to do.</dd>
</div>

<div>
<dt>Resolved</dt>
<dt><span className="craik-fields__type"><code>resolved_at</code> · <code>resolved_by_receipt_id</code></span></dt>
<dd>Must include the resolution timestamp and the operator receipt that closed the debt record.</dd>
</div>

</div>

## Resolution

`resolve_context_debt` is a store-backed transition helper. It loads
the debt record, mints or links an operator receipt, writes the updated
record, and returns the persisted resolved form. Operators can exercise
the same path from the CLI:

```bash
craik knowledge resolve-context-debt context_debt_task_docs_missing_external_state_github \
  --summary "GitHub state was refreshed."
```

The command requires an active operator session. The output includes
`resolved_by_receipt_id`, and the receipt is persisted in the local
store for later operator review.

## Handoff summary

Handoffs continue to expose a deterministic `context_debt` summary
list for runner readability. The structured records persist
separately.

## What's next

<div className="craik-next">

<a href="../../guides/context-budgeting/">
<strong>Guide</strong>
<span>Context budgeting</span>
<small>How case-file omissions become debt.</small>
</a>

<a href="../evidence-assumption-view/">
<strong>Reference</strong>
<span>Evidence and assumption view</span>
<small>The operator surface where unresolved debt surfaces.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The <code>context_debt_record</code> shape.</small>
</a>

</div>
