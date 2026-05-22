# Scheduled task creation

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The helper that converts one cron-like gateway schedule tick into one
deterministic `craik.task_request` — cron shape, task context,
deduplication, and limitations.

</div>

<div className="craik-keypoint">

**Validation + conversion, not execution.**

`craik.runtime.schedules` does not run a scheduler loop. It validates
schedule definitions and converts an observed tick into a task while
preserving gateway context.

</div>

## Cron shape

Conservative five-field cron-like expression. Supported field
characters: digits, `*`, `/`, `,`, `-`. The minute field must not
schedule work more often than every five minutes; `* * * * *` and
`*/4 * * * *` are rejected by default.

```text
0 9 * * *
*/15 9-17 * * 1,2,3,4,5
```

<div className="craik-keypoint">

**No named shortcuts.**

Named shortcuts such as <code>@daily</code> are not supported.

</div>

## Task context

Created tasks preserve:

<div className="craik-grid">

<div><h4>Schedule id</h4></div>
<div><h4>Schedule tick id</h4></div>
<div><h4>Cron expression</h4></div>
<div><h4>Run timestamp</h4></div>
<div><h4>Project id</h4></div>
<div><h4>Policy envelope id</h4></div>
<div><h4>Channel</h4></div>
<div><h4>Linked receipt ids</h4></div>

</div>

The task id is deterministic from schedule id and tick id.

## Deduplication

Callers pass the set of already-seen tick ids. If the tick id was
already seen, task creation returns `created = false` and does not
create another `TaskRequest`.

## Limitations

<div className="craik-keypoint">

**No execution, no persistence, no clock.**

Future gateway scheduling layers are responsible for tracking seen
ticks, persisting tasks, and emitting schedule execution receipts.

</div>

## What's next

<div className="craik-next">

<a href="../scheduled-automations/">
<strong>Reference</strong>
<span>Scheduled automations</span>
<small>The wider automation contract this helper supports.</small>
</a>

<a href="../gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>The receipt shape schedule execution produces.</small>
</a>

<a href="../../guides/gateway-troubleshooting/">
<strong>Guide</strong>
<span>Gateway troubleshooting</span>
<small>Diagnose schedule problems.</small>
</a>

</div>
