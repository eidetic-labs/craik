# Known traps view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator display for `craik.known_trap` and
`craik.negative_knowledge` records through `craik operator traps`:
what the v0.7.0 operator surface formats, how state boundaries are
preserved, and the review boundary.

</div>

<div className="craik-keypoint">

**Review aids, not policy.**

Known traps and negative knowledge help agents avoid repeated
mistakes. They do not override policy, resolve contradictions, or
prove absence without the cited evidence.

</div>

## Commands

```bash
craik operator traps
craik operator traps --project PROJECT_ID
craik operator traps --task-id TASK_ID
craik operator traps --json
```

`craik operator traps` prints the current known traps and negative
knowledge review view. The JSON form emits the same timestamped
snapshot for tooling, with optional project and task filters applied.

## What it formats

<div className="craik-grid">

<div><h4>Trap statement · kind · project · task · status</h4></div>
<div><h4>Avoidance guidance</h4></div>
<div><h4>Evidence · handoff · contradiction links</h4></div>
<div><h4>Expiry timestamps</h4></div>
<div><h4>Negative knowledge scope &amp; trust class</h4></div>

</div>

## State boundaries

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Display</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Active</dt>
<dt><span className="craik-fields__type">current</span></dt>
<dd>Use as current guidance.</dd>
</div>

<div>
<dt>Expired</dt>
<dt><span className="craik-fields__type">audit-only</span></dt>
<dd>Visible for audit. Don't treat as current guidance without review.</dd>
</div>

<div>
<dt>Contradicted</dt>
<dt><span className="craik-fields__type">conflict</span></dt>
<dd>Visible so operators can inspect the conflict before relying on the trap or negative statement.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../known-traps/">
<strong>Reference</strong>
<span>Known traps</span>
<small>The underlying contract behavior.</small>
</a>

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../freshness/">
<strong>Reference</strong>
<span>Freshness</span>
<small>How expiry interacts with stale-risk warnings.</small>
</a>

</div>
