# Migration Reports

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The safe-to-share report generated from an adjacent runtime migration
plan. Reports summarize what can import automatically, what needs
manual review, which secrets were skipped, and which validation steps
remain before apply mode is considered.

</div>

<div className="craik-keypoint">

**Reports explain the migration without carrying source secrets.**

Every item links a source object to its proposed Craik target object.
Secret-like source fields are listed by field path only; raw values are
not included in JSON output, text output, receipts, logs, or docs
examples.

</div>

## Command

```bash
craik migrate report --source ./adjacent-runtime --kind agent-runtime
```

Use JSON output for automation:

```bash
craik migrate report --source ./adjacent-runtime --kind agent-runtime --json
```

## Sections

<div className="craik-fields">

<div>
<dt>Section</dt>
<dt><span className="craik-fields__type">Purpose</span></dt>
<dd>Notes</dd>
</div>

<div><dt><code>summary</code></dt><dt><span className="craik-fields__type">counts</span></dt><dd>Counts object maps by importable, partial, manual, unsupported, and skipped-secret status.</dd></div>
<div><dt><code>importable_objects</code></dt><dt><span className="craik-fields__type">automatic</span></dt><dd>Objects with a direct target schema and target id.</dd></div>
<div><dt><code>manual_actions</code></dt><dt><span className="craik-fields__type">operator review</span></dt><dd>Partial or manual objects that require operator action before import or enablement.</dd></div>
<div><dt><code>skipped_secrets</code></dt><dt><span className="craik-fields__type">redacted</span></dt><dd>Secret-bearing objects with skipped field paths and reconfiguration actions.</dd></div>
<div><dt><code>security_posture_changes</code></dt><dt><span className="craik-fields__type">risk review</span></dt><dd>Authority boundaries that change during migration, such as gateway, sandbox, channel, approval, or credential posture.</dd></div>
<div><dt><code>unsupported_capabilities</code></dt><dt><span className="craik-fields__type">blocked</span></dt><dd>Objects with no defined Craik migration target.</dd></div>
<div><dt><code>recommended_next_commands</code></dt><dt><span className="craik-fields__type">next steps</span></dt><dd>Commands for re-running plans, reconfiguring providers, or inspecting unsupported source state.</dd></div>
<div><dt><code>validation_checklist</code></dt><dt><span className="craik-fields__type">release gate</span></dt><dd>Checks operators must complete before moving from dry-run to apply-mode migration.</dd></div>

</div>

## Determinism

Report items are sorted by source id. Re-running a report over the
same source state produces stable section ordering and status counts,
which makes the output suitable for review, CI snapshots, and release
readiness evidence.

## What's Next

<div className="craik-next">

<a href="../migration-maps/">
<strong>Reference</strong>
<span>Migration maps</span>
<small>The object map source for migration reports.</small>
</a>

<a href="../secret-migration-policy/">
<strong>Reference</strong>
<span>Secret migration policy</span>
<small>How skipped secrets are handled.</small>
</a>

<a href="../../guides/adjacent-runtime-migration/">
<strong>Guide</strong>
<span>Adjacent runtime migration</span>
<small>Run inspect, plan, report, and import dry-runs.</small>
</a>

</div>
