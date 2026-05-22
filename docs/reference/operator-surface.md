# Operator surface

<p className="craik-meta"><span>4 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator surface Craik ships, the formatter contracts
behind each view, and the boundary between the CLI-first surface and a
complete dashboard.

</div>

<div className="craik-keypoint">

**Craik chose a CLI-first operator surface for v0.7.0.**

The shipped entrypoint is `craik operator overview`: a read-only,
terminal-friendly surface backed by local-store queries and validated
formatter contracts. A complete TUI or dashboard is post-MVP scope.
See [Post-MVP Scope](post-mvp-scope.md).

</div>

## Why CLI-first

<div className="craik-grid">

<div><h4>Same terminal</h4><p>Works where agents and operators already run Craik.</p></div>
<div><h4>No service required</h4><p>Inspects local SQLite state without starting a process.</p></div>
<div><h4>Keeps review simple</h4><p>Read-only workflows stay lightweight.</p></div>
<div><h4>Avoids premature complexity</h4><p>No browser, server, auth, or asset concerns before views are proven.</p></div>
<div><h4>Future-compatible</h4><p>Dashboard views can reuse the same formatter contracts.</p></div>

</div>

## Boundary

<div className="craik-keypoint">

**Read-only by default.**

The v0.7.0 operator surface displays state from the local store and
validated contracts. It must not mutate memory, approve grants,
resolve contradictions, delete records, or execute plugins without an
explicit future command and policy boundary.

</div>

## Commands

The shared overview command prints the current project state grouped by
operator question.

```bash
craik operator overview
craik operator overview --project project_docs
craik operator overview --section inbox
craik operator overview --json
```

`--project` scopes records that carry a project id or link to a task in
that project. Global records without project or task scope remain
visible because hiding them would imply a relationship Craik cannot
prove from the persisted record.

The JSON payload is the same read-only snapshot used by the text view:
`project_id`, `read_only`, `sections`, and `notes`. Every section names
the navigation id, count, status, suggested command, backing contract
kinds, and a short summary.

## Navigation

The CLI surface organizes views around operator questions. The first
command is an overview; follow-on commands can reuse the same section
ids and formatter contracts.

<div className="craik-grid">

<div><h4>Overview</h4><p>Project · active tasks · recent handoffs · blocked states.</p></div>
<div><h4>Work Graph</h4><p>Graph events · exports · dependencies · verification links.</p></div>
<div><h4>Handoffs</h4><p>Summaries · next steps · receipts · evidence · risks.</p></div>
<div><h4>Receipts</h4><p>Capability and plugin action records.</p></div>
<div><h4>Inbox</h4><p>Contradictions · delegations · context requests.</p></div>
<div><h4>Evidence</h4><p>References · assumptions · memory impact previews.</p></div>
<div><h4>Quality</h4><p>Quality scores · critic findings · red-team findings · gates.</p></div>
<div><h4>Instructions</h4><p>Sources · snapshots · distilled proposals · reviews.</p></div>
<div><h4>Traps</h4><p>Known traps · negative knowledge.</p></div>
<div><h4>Run Deltas</h4><p>Recovery and continuity changes.</p></div>

</div>

Each view degrades cleanly when records are missing. Missing data is
shown as unavailable state — never inferred.

## Data sources

The initial surface reads from existing contracts and store helpers.

<div className="craik-grid">

<div><h4><code>craik.handoff</code></h4></div>
<div><h4><code>craik.capability_receipt</code></h4></div>
<div><h4><code>craik.plugin_receipt</code></h4></div>
<div><h4><code>craik.work_graph_event</code></h4></div>
<div><h4><code>craik.contradiction_report</code></h4></div>
<div><h4><code>craik.evidence_reference</code></h4></div>
<div><h4><code>craik.assumption</code></h4></div>
<div><h4><code>craik.memory_impact_preview</code></h4></div>
<div><h4><code>craik.human_delegation_point</code></h4></div>
<div><h4><code>craik.context_request</code></h4></div>
<div><h4><code>craik.handoff_quality_score</code></h4></div>
<div><h4><code>craik.evidence_coverage_score</code></h4></div>
<div><h4><code>craik.runtime_critic_finding</code></h4></div>
<div><h4><code>craik.red_team_finding</code></h4></div>
<div><h4><code>craik.instruction_source</code></h4></div>
<div><h4><code>craik.distilled_instruction_proposal</code></h4></div>
<div><h4><code>craik.known_trap</code></h4></div>
<div><h4><code>craik.negative_knowledge</code></h4></div>
<div><h4><code>craik.run_delta</code></h4></div>

</div>

See the [schema reference](schemas.md) for the persisted field shapes
of each contract.

## Follow-on surfaces

Future TUI or dashboard work can reuse the overview snapshot and
individual formatter contracts behind the same read-only boundary.
Each new command or panel should have focused tests for formatting,
empty-state behavior, project scoping, and links to the underlying
contracts before it is described as operational.

## What's next

<div className="craik-next">

<a href="../post-mvp-scope/">
<strong>Reference</strong>
<span>Post-MVP scope</span>
<small>What a full dashboard would add beyond the preview surface.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>The persisted contracts these views read.</small>
</a>

<a href="../handoff-viewer/">
<strong>Reference</strong>
<span>Handoff viewer</span>
<small>The first operator-surface contract.</small>
</a>

</div>
