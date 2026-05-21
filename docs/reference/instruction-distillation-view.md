# Instruction distillation view

<p className="craik-meta"><span>2 min read</span><span>Reference · preview</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The read-only operator display for declared instruction sources,
source snapshots, provenance records, distilled proposals, and
promotion reviews. The view exposes the audit trail behind every
runtime instruction.

</div>

<div className="craik-keypoint">

**Proposals are review records, not authority.**

Distilled proposals never become runtime authority on their own. Only
promoted constraints participate in compiled prompts.

</div>

## What it formats

<div className="craik-grid">

<div><h4>Declared instruction sources</h4><p>And their trust boundaries.</p></div>
<div><h4>Source snapshot hash status</h4></div>
<div><h4>Provenance records</h4><p>And source ranges.</p></div>
<div><h4>Distilled proposals</h4><p>By promotion status.</p></div>
<div><h4>Promotion reviews</h4><p>Linked receipts · handoffs · policy envelope.</p></div>

</div>

## Review flow

<div className="craik-fields">

<div>
<dt>Proposal state</dt>
<dt><span className="craik-fields__type">Display</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Proposed / rejected / deferred / stale / contradicted</dt>
<dt><span className="craik-fields__type">inactive</span></dt>
<dd>Visible so an operator can audit why the instruction did not become active.</dd>
</div>

<div>
<dt>Approved</dt>
<dt><span className="craik-fields__type">active</span></dt>
<dd>Shows the promoted constraint ID. Without a promoted constraint ID, the proposal is displayed as inactive even when it has provenance, evidence, or prior review notes.</dd>
</div>

</div>

## Trust boundaries

<div className="craik-keypoint">

**Source authority is preserved.**

Sources include their owner and trust boundary. The view preserves
those fields so operators can distinguish repository, project,
organization, user, and external instruction authority before
promoting a distilled instruction.

</div>

## What's next

<div className="craik-next">

<a href="../instruction-sources/">
<strong>Reference</strong>
<span>Instruction sources</span>
<small>The declared-source registry.</small>
</a>

<a href="../instruction-distillation-workflow/">
<strong>Reference</strong>
<span>Instruction distillation workflow</span>
<small>The pipeline this view audits.</small>
</a>

<a href="../distilled-instructions/">
<strong>Reference</strong>
<span>Distilled instructions</span>
<small>Proposal states, categories, provenance, and snapshots.</small>
</a>

<a href="../operator-surface/">
<strong>Reference</strong>
<span>Operator surface</span>
<small>The shared TUI boundary.</small>
</a>

</div>
