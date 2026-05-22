# Handoff viewer

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only `craik operator handoff` view over `craik.handoff`
records, what it formats, and the redaction boundary it preserves.

</div>

<div className="craik-keypoint">

**Design rationale: [ADR 0005 · Receipts and handoffs as public contracts](../adr/0005-receipts-and-handoffs-as-public-contracts.md).**

</div>

## What the surface formats

<div className="craik-grid">

<div><h4>Handoff id · task id · project id · status · agent · summary</h4></div>
<div><h4>Completed actions</h4></div>
<div><h4>Next steps</h4></div>
<div><h4>Receipt links</h4></div>
<div><h4>Evidence-like artifacts</h4><p>And changed files.</p></div>
<div><h4>Risks</h4></div>
<div><h4>Open follow-ups</h4><p>Context debt · assumptions · contradictions · human delegation ids.</p></div>

</div>

## Boundaries

<div className="craik-keypoint">

**Read durable summaries, not raw logs.**

The viewer displays the durable summary already captured in the
handoff and linked ids for deeper inspection. It must not read raw
logs or expand potentially sensitive command output.

</div>

Missing sections render as `none` so operators can distinguish an
empty section from a formatter failure.

## Commands

```bash
craik operator handoff handoff_docs
craik operator handoff task_docs
craik operator handoff task_docs --json
```

The command accepts either a handoff id or a task id. The text view
uses the operator formatter for terminal scanning. `--json` returns
the persisted `craik.handoff` payload for tooling and exact contract
inspection.

## What's next

<div className="craik-next">

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../receipt-viewer/">
<strong>Reference</strong>
<span>Receipt viewer</span>
<small>The receipts the handoff links to.</small>
</a>

<a href="../../adr/receipts-and-handoffs-as-public-contracts/">
<strong>ADR</strong>
<span>0005 · Receipts &amp; handoffs as public contracts</span>
<small>Why handoffs are first-class.</small>
</a>

</div>
