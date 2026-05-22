# Scheduled automations

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

`craik.scheduled_automation` and `craik.gateway_schedule` — enabled
gateway definitions backed by persisted cron-like schedules, evaluated
one tick at a time, with deduplication and redacted receipts.

</div>

<div className="craik-keypoint">

**Observation only.**

Scheduled automations do not run a clock or execute created tasks.
They preserve the boundary between schedule observation, task
creation, and later task execution under policy.

</div>

## Enforcement

`craik.runtime.scheduled_automations` enforces:

<div className="craik-grid">

<div><h4>Explicit enabled state</h4></div>
<div><h4>Policy envelope checks</h4></div>
<div><h4>Narrow <code>gateway.schedule.execute</code> authority</h4></div>
<div><h4>Schedule tick deduplication</h4></div>
<div><h4>Redacted automation receipts</h4></div>

</div>

## Persistence

Gateway schedules and scheduled automations are first-class local-store
contracts. Use the typed store helpers to round-trip them alongside
channel adapter contracts, identity pairings, allowlists, policy
envelopes, and gateway receipts:

```python
store.put_gateway_schedule(schedule)
store.put_scheduled_automation(automation)
store.put_gateway_receipt(receipt)
```

## Execution boundary

An automation creates a task only when **every** condition holds.

<ol className="craik-steps">
<li>The automation is enabled.</li>
<li>Policy allows <code>gateway.schedule.execute</code>.</li>
<li>The tick id has not already created a task.</li>
<li>The schedule expression is valid.</li>
</ol>

Disabled, policy-denied, and duplicate ticks do not create tasks.

## Receipts

Automation receipts record:

<div className="craik-grid">

<div><h4>Policy envelope id</h4></div>
<div><h4>Automation id</h4></div>
<div><h4>Schedule id</h4></div>
<div><h4>Tick id</h4></div>
<div><h4>Created task id</h4><p>When one exists.</p></div>

</div>

Receipts use `gateway.schedule.execute` and stay redacted.

## What's next

<div className="craik-next">

<a href="../scheduled-task-creation/">
<strong>Reference</strong>
<span>Scheduled task creation</span>
<small>The helper that converts one tick into a task.</small>
</a>

<a href="../gateway-daemon/">
<strong>Reference</strong>
<span>Gateway daemon</span>
<small>The foreground local daemon and its current dispatch boundary.</small>
</a>

<a href="../gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>The receipt shape automations produce.</small>
</a>

</div>
