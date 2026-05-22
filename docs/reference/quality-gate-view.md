# Quality gate view

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator display for handoff quality scores, evidence
coverage, runtime critic findings, and red-team findings — what it
formats and the gate states it reports through `craik operator
quality`.

</div>

<div className="craik-keypoint">

**Display only, never authority.**

The gate state does not mutate policy or approve work. It is a compact
operator summary of the underlying contracts.

</div>

## Commands

```bash
craik operator quality
craik operator quality --json
```

`craik operator quality` prints the terminal gate view. `--json`
emits the same read-only snapshot for tooling with `handoff_scores`,
`evidence_scores`, `critic_findings`, and `red_team_findings` arrays.

## What it formats

<div className="craik-grid">

<div><h4>Handoff score bands</h4><p>And blocking reasons.</p></div>
<div><h4>Evidence coverage scores</h4><p>Missing evidence and weak claims.</p></div>
<div><h4>Critic findings</h4><p>By review status and severity.</p></div>
<div><h4>Red-team findings</h4><p>Including blocking state.</p></div>
<div><h4>Adjudication links</h4><p>When a finding has been reviewed.</p></div>

</div>

## Gate states

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Trigger</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>blocked</code></dt>
<dt><span className="craik-fields__type">attention needed</span></dt>
<dd>Handoff or evidence score is poor, or an unadjudicated red-team finding is blocking.</dd>
</div>

<div>
<dt><code>reviewable</code></dt>
<dt><span className="craik-fields__type">review pending</span></dt>
<dd>High or critical critic findings remain reviewable, or any score is adequate rather than excellent.</dd>
</div>

<div>
<dt><code>clear</code></dt>
<dt><span className="craik-fields__type">no attention</span></dt>
<dd>No scores or findings require operator attention.</dd>
</div>

</div>

## Authority boundary

<div className="craik-keypoint">

**Findings are non-authoritative.**

Runtime critic and red-team findings remain non-authoritative unless a
separate adjudication accepts, revises, rejects, or defers them. The
view shows <code>authoritative=false</code> and any adjudication ID so
operators can distinguish review signals from accepted decisions.

</div>

## What's next

<div className="craik-next">

<a href="../quality-scores/">
<strong>Reference</strong>
<span>Quality scores</span>
<small>The underlying contracts.</small>
</a>

<a href="../runtime-critics/">
<strong>Reference</strong>
<span>Runtime critics &amp; red team</span>
<small>The reviewable findings.</small>
</a>

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

</div>
