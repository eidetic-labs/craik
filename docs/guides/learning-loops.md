# Learning loops

<p className="craik-meta"><span>4 min read</span><span>For maintainers</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Walk through Craik's learning-loop discipline — telemetry, proposals,
replay, receipts, promotion gates, rollbacks, and trajectory exports.
Loops turn observed skill behavior into reviewable improvement
records. They never let an agent silently rewrite reusable guidance.

</div>

<div className="craik-keypoint">

**No silent self-modification.**

A skill proposal becomes promoted guidance only after explicit approval
by a non-agent reviewer. Missing promotion gates produce a denied
decision — and denied decisions are valuable review artifacts.

</div>

## Supported flow

<ol className="craik-steps">
<li>Record <a href="../../reference/skill-telemetry/">skill telemetry</a> for an invocation.</li>
<li>Draft a <a href="../../reference/skill-proposals/">skill proposal</a> from telemetry, evidence, and receipts.</li>
<li>Run <a href="../../reference/skill-replay/">skill replay</a> against redacted fixtures.</li>
<li>Record review, replay, promotion, rollback, and export decisions with <a href="../../reference/learning-receipts/">learning receipts</a>.</li>
<li>Apply <a href="../../reference/skill-promotion-gates/">skill promotion gates</a> before promoted guidance changes.</li>
<li>Use <a href="../../reference/skill-rollbacks/">skill rollbacks</a> when a promoted version regresses.</li>
<li>Use <a href="../../reference/trajectory-exports/">training trajectory exports</a> and compressed summaries for replay and review.</li>
</ol>

Learning loops can also use
[memory review nudges](../reference/memory-review-nudges.md) and
[preference facts](../reference/preference-facts.md) when repeated
behavior suggests a reviewable memory update or preference
clarification.

## Operator commands

Craik exposes the learning-loop posture through guarded skill commands:

```sh
craik skills telemetry
craik skills proposals
craik skills eval
craik skills promote skill_proposal_docs --dry-run
craik skills rollback skill_docs --dry-run
craik skills history
```

These commands require an active operator session. Promotion and rollback
commands default to dry-run posture and do not silently change reusable
guidance. They report the missing gates until approval, replay evidence,
and receipts exist.

## Evidence boundary

Every learning-loop step preserves ids — not raw payloads.

<div className="craik-grid">

<div><h4>Task ids</h4></div>
<div><h4>Policy envelope ids</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Receipt ids</h4></div>
<div><h4>Telemetry ids</h4></div>
<div><h4>Replay fixture ids</h4></div>
<div><h4>Replay result ids</h4></div>
<div><h4>Proposal ids</h4></div>
<div><h4>Promoted version ids</h4></div>
<div><h4>Rollback version ids</h4></div>
<div><h4>Unresolved risk ids</h4></div>

</div>

<div className="craik-keypoint">

**Redact before persistence.**

Telemetry, receipts, proposals, exports, and summaries redact secrets,
private prompts, private payloads, raw outputs, traces, trajectories,
credentials, and local-only filesystem paths.

</div>

## Promotion requirements

A proposal can become promoted guidance only after every requirement
below is satisfied.

<div className="craik-grid">

<div><h4>Approved proposal</h4></div>
<div><h4>Structured improvement plan</h4></div>
<div><h4>Non-agent approver</h4></div>
<div><h4>Policy envelope context</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Eval or replay result ids</h4></div>
<div><h4>Receipt ids</h4></div>
<div><h4>Approval receipt id</h4></div>

</div>

Missing promotion gates produce a denied promotion decision. Denied
decisions are review artifacts and must keep explicit denial reasons.

## Rollback requirements

Rollbacks target a prior promoted version. A rollback decision
preserves:

<div className="craik-grid">

<div><h4>Promoted version id</h4></div>
<div><h4>Rollback version id</h4></div>
<div><h4>Rollback reason &amp; rationale</h4></div>
<div><h4>Policy envelope context</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Receipt ids</h4></div>
<div><h4>Replay result ids</h4></div>
<div><h4>Rollback decision receipt</h4></div>

</div>

<div className="craik-keypoint">

**Rollbacks don't invent replacement guidance.**

A rollback moves back to a known prior version and leaves an audit
trail. It is not a hook for silently substituting new guidance.

</div>

## Trajectory review

Training trajectory exports are redacted replay and review artifacts.

<div className="craik-decision">

<div>
<h4>Full exports</h4>
<p>Keep decision-level detail. Use these when reviewers need diagnostics, artifacts, observed output, or per-step timestamps.</p>
</div>

<div>
<h4>Compressed summaries</h4>
<p>Keep only the links needed for review: receipt ids · evidence ids · policy envelope ids · replay fixture ids · replay result ids · unresolved risk ids. Omit decision detail by design.</p>
</div>

</div>

## Safe diagnostics

```sh
uv run --extra dev ruff check .
uv run --extra dev mypy
uv run --extra dev pytest tests/test_skill_telemetry.py tests/test_skill_proposals.py tests/test_skill_replay.py
uv run --extra dev pytest tests/test_learning_receipts.py tests/test_skill_promotions.py tests/test_skill_rollbacks.py
uv run --extra dev pytest tests/test_trajectory_exports.py tests/test_docs.py
```

Expected: `All checks passed!` · `Success: no issues found` · `passed`.

If a command fails, preserve the command, failing test name, and
sanitized error summary in a receipt or review note. **Do not copy raw
prompts, credentials, private payloads, or local-only paths into
public docs.**

## What's next

<div className="craik-next">

<a href="../../reference/skill-promotion-gates/">
<strong>Reference</strong>
<span>Skill promotion gates</span>
<small>The shipped gates a proposal must satisfy.</small>
</a>

<a href="../../reference/learning-receipts/">
<strong>Reference</strong>
<span>Learning receipts</span>
<small>The receipt shape every learning decision produces.</small>
</a>

<a href="../../reference/trajectory-exports/">
<strong>Reference</strong>
<span>Trajectory exports</span>
<small>The replay-and-review artifact shape.</small>
</a>

</div>
