# Evidence and assumption view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only `craik operator evidence` view over
`craik.evidence_reference` and `craik.assumption` records, what it
formats, and the boundary that keeps assumptions visually separate
from evidence.

</div>

<div className="craik-keypoint">

**Assumptions are not facts.**

The view keeps assumptions visually separate from evidence and shows
confidence and status so operators can review whether an assumption is
open, validated, or rejected.

</div>

## What it formats

<div className="craik-decision">

<div>
<h4>Evidence</h4>
<ul>
<li>Evidence id and kind</li>
<li>Source and locator</li>
<li>Capture timestamp when present</li>
<li>Summary</li>
</ul>
</div>

<div>
<h4>Assumptions</h4>
<ul>
<li>Assumption id and status</li>
<li>Task id</li>
<li>Confidence</li>
<li>Linked evidence ids</li>
<li>Statement</li>
</ul>
</div>

</div>

## Boundaries

<div className="craik-keypoint">

**Read-only.**

Missing evidence or assumptions render as `none`. The view does not
validate, reject, promote, or write memory facts.

</div>

## Commands

```bash
craik operator evidence
craik operator evidence --task-id task_docs
craik operator evidence --json
```

The command lists evidence and assumptions together but keeps them in
separate sections. `--task-id` filters assumptions by task id and
includes global evidence plus evidence explicitly tagged with matching
`metadata.task_id`. `--json` returns separate `evidence` and
`assumptions` arrays for tooling.

## What's next

<div className="craik-next">

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

<a href="../../guides/evidence-and-assumptions/">
<strong>Guide</strong>
<span>Evidence and assumptions</span>
<small>The operator workflow this view supports.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The <code>evidence_reference</code> and <code>assumption</code> shapes.</small>
</a>

</div>
