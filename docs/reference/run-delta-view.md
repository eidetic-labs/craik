# Run delta view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator display for continuity-relevant changes since
the previous usable handoff or resume point — and the inspection
boundary that keeps it honest.

</div>

<div className="craik-keypoint">

**Summarizes; doesn't inspect.**

Run deltas summarize already-persisted local state. `craik run delta`
reads those durable records by delta id, run id, or task id and renders
the operator view. Add `--json` to return the same delta and linked
recovery sessions for automation. The view does not
inspect the working tree, refresh GitHub, query Stigmem, or decide
whether a run can continue.

</div>

## Commands

```bash
craik operator run-delta DELTA_ID_OR_RUN_ID_OR_TASK_ID
craik operator run-deltas DELTA_ID_OR_RUN_ID_OR_TASK_ID
craik operator run-delta DELTA_ID_OR_RUN_ID_OR_TASK_ID --json
```

`craik operator run-delta` and `craik operator run-deltas` are
read-only operator-surface aliases. They resolve a persisted run delta
by delta ID first, then run ID, then task ID, and include linked
recovery sessions in both terminal and JSON output.

## What it formats

<div className="craik-grid">

<div><h4>Previous and current handoff links</h4></div>
<div><h4>Case file · receipt · contradiction · active instruction constraint links</h4></div>
<div><h4>Created · updated · removed · unchanged change items</h4></div>
<div><h4>Linked recovery sessions</h4></div>
<div><h4>Required actions and stale-risk warnings</h4><p>For non-clean recovery.</p></div>

</div>

## Recovery links

<div className="craik-keypoint">

**Resume must read required actions.**

A clean session may have no required actions. Changed or missing
context must show required actions so agents do not continue silently
through stale or incomplete state.

</div>

## What's next

<div className="craik-next">

<a href="../recovery/">
<strong>Reference</strong>
<span>Recovery mode</span>
<small>The underlying contract behavior.</small>
</a>

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The <code>run_delta</code> and <code>recovery_session</code> shapes.</small>
</a>

</div>
