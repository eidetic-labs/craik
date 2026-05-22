# Contradiction inbox view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only `craik operator contradictions` view over
`craik.contradiction_report` records, what it formats, and the
review-only boundary it preserves.

</div>

<div className="craik-keypoint">

**Review only.**

The view surfaces state and supporting links — it does not resolve,
ignore, or mutate contradictions.

</div>

## What it formats

<div className="craik-grid">

<div><h4>Inbox count</h4></div>
<div><h4>Contradiction id and status</h4></div>
<div><h4>Task id</h4></div>
<div><h4>Owner or unassigned</h4></div>
<div><h4>Summary</h4></div>
<div><h4>Proposed resolution</h4></div>
<div><h4>Affected artifacts</h4></div>
<div><h4>Evidence links</h4></div>

</div>

## Statuses

The inbox displays open, resolved, and ignored contradiction reports.

## Commands

```bash
craik operator contradictions
craik operator contradictions --task-id task_docs
craik operator contradictions --status open
craik operator contradictions --json
```

The command lists reports with optional task and status filters. The
text view is optimized for operator scanning; `--json` returns the
persisted contradiction report payloads for tooling and exact contract
inspection.

## Boundaries

<div className="craik-keypoint">

**Use linked evidence before promoting any resolution.**

Missing owners render as `unassigned`. Missing artifact or evidence
links render as `none`. Operators use the linked evidence and affected
artifacts before promoting any resolution to durable memory.

</div>

## What's next

<div className="craik-next">

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../../guides/contradiction-inbox/">
<strong>Guide</strong>
<span>Contradiction inbox</span>
<small>The operator workflow this view supports.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The <code>contradiction_report</code> shape this view reads.</small>
</a>

</div>
