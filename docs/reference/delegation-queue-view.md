# Delegation queue view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only `craik operator delegations` view over
`craik.human_delegation_point` records, supported statuses, and the
inspection-only boundary.

</div>

<div className="craik-keypoint">

**Make pending approvals easy to find.**

Open items show pending approvals, clarifications, escalations, or
ownership transfers so operators can act on them quickly.

</div>

## What it formats

<div className="craik-grid">

<div><h4>Delegation count</h4></div>
<div><h4>Delegation id · status · kind</h4></div>
<div><h4>Task id</h4></div>
<div><h4>Owner or unassigned</h4></div>
<div><h4>Requester</h4></div>
<div><h4>Requested decision</h4></div>
<div><h4>Summary</h4></div>
<div><h4>Policy envelope link</h4></div>
<div><h4>Receipt links</h4></div>
<div><h4>Resolution</h4><p>When present.</p></div>

</div>

## Statuses

The queue displays open, resolved, and cancelled delegation points.

## Boundaries

<div className="craik-keypoint">

**Inspection only.**

The queue does not approve, cancel, or resolve delegation points. It
shows auditable state so operators know where human input is needed or
already recorded.

</div>

## Commands

```bash
craik operator delegations
craik operator delegations --task-id task_docs
craik operator delegations --status open
craik operator delegations --json
```

The command lists delegation points with optional task and status
filters. The text view is optimized for pending human-attention scans;
`--json` returns the persisted delegation payloads for tooling.

## What's next

<div className="craik-next">

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../human-delegation/">
<strong>Reference</strong>
<span>Human delegation</span>
<small>The contract this view reads.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The <code>human_delegation_point</code> shape.</small>
</a>

</div>
