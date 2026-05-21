# Distilled instructions

<p className="craik-meta"><span>5 min read</span><span>Reference</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The lifecycle, category taxonomy, provenance links, and snapshot rules
behind Craik's distilled instruction proposals. Use this page to
understand what the runtime stores before an instruction can become an
active constraint.

</div>

<div className="craik-keypoint">

**Distillation creates proposals, not authority.**

Parsed instruction text becomes reviewable evidence. Only an explicit
approval can move a proposal into the governing set used by case files
and compiled prompts.

</div>

## Lifecycle

<div className="craik-fields">

<div>
<dt>Status</dt>
<dt><span className="craik-fields__type">Authority</span></dt>
<dd>Meaning</dd>
</div>

<div>
<dt><code>proposed</code></dt>
<dt><span className="craik-fields__type">inactive</span></dt>
<dd>Extracted, provenanced, categorized, and waiting for operator review.</dd>
</div>

<div>
<dt><code>governing</code></dt>
<dt><span className="craik-fields__type">active</span></dt>
<dd>Approved by an operator and backed by a promoted instruction constraint.</dd>
</div>

<div>
<dt><code>rejected</code></dt>
<dt><span className="craik-fields__type">inactive</span></dt>
<dd>Denied by an operator with a review receipt.</dd>
</div>

<div>
<dt><code>deferred</code></dt>
<dt><span className="craik-fields__type">inactive</span></dt>
<dd>Held back because the source is stale, missing, newly observed, omitted, or contradicted.</dd>
</div>

<div>
<dt><code>superseded</code></dt>
<dt><span className="craik-fields__type">inactive</span></dt>
<dd>Replaced by a newer proposal or review path while preserving audit history.</dd>
</div>

</div>

Stale or contradicted proposals remain visible for review, but they do
not participate in `list_governing`, case-file assembly, or prompt
compilation unless an operator approves them with an explicit override
rationale.

## Categories

Craik categorizes extracted statements deterministically. Each
proposal records the matched rule name and confidence so later
reviewers can explain why a statement entered a category.

| Category | Use |
| --- | --- |
| `policy` | Approval, governance, or authority requirements. |
| `security_rule` | Secret handling, sandboxing, safety, or security-sensitive requirements. |
| `boundary` | Scope, ownership, repository, or authority boundaries. |
| `command` | Required or forbidden commands and validation steps. |
| `instruction` | General runtime guidance for agents. |
| `handoff_rule` | Requirements for durable handoff content or timing. |
| `memory_rule` | Rules for memory reads, writes, proposals, and promotion. |
| `preference` | Stable user, team, or project preferences. |
| `stale_risk` | Warnings that context may become outdated or unsafe. |

Unclassified candidates are not promoted into proposals silently.
They are returned in ingestion summaries as warnings for operator
review.

## Provenance

Every proposal links back to the source text that produced it:

<div className="craik-grid">

<div><h4>Source ID</h4><p>The registered instruction source.</p></div>
<div><h4>Snapshot ID</h4><p>The observed source hash state.</p></div>
<div><h4>Provenance IDs</h4><p>The extracted source ranges.</p></div>
<div><h4>Evidence IDs</h4><p>Receipts and supporting review records.</p></div>
<div><h4>Excerpt hash</h4><p>A stable digest of the extracted statement.</p></div>
<div><h4>Summary</h4><p>The first non-empty statement line, capped for display.</p></div>

</div>

Line ranges are precise when the parser can identify stable lines.
Partial ranges are rejected because they make review ambiguous. When a
stable range is not available, the provenance record falls back to the
source-level reference instead of inventing a line number.

## Snapshot linkage

`craik.instruction_source_snapshot` records whether a registered
source is `new`, `unchanged`, `changed`, or `missing`. Proposal state
follows that snapshot history:

<ol className="craik-steps">
<li>An unchanged source can keep its existing proposals reviewable.</li>
<li>A changed source defers prior proposals until the new text is reviewed.</li>
<li>A missing source defers proposals derived from that source.</li>
<li>A newly observed source produces new proposed items rather than active constraints.</li>
</ol>

Case files and prompts consume only governing constraints. Compiled
prompts render them in the `Active instruction constraints` section as
`(category) statement [source_id @ path:line-range]`, sorted by
category, source ID, and statement.

## What's next

<div className="craik-next">

<a href="../instruction-sources/">
<strong>Reference</strong>
<span>Instruction sources</span>
<small>The declared source registry and trust boundary contract.</small>
</a>

<a href="../instruction-approval/">
<strong>Reference</strong>
<span>Instruction approval</span>
<small>The review receipts and override path that activate constraints.</small>
</a>

<a href="../../guides/managing-instructions/">
<strong>Guide</strong>
<span>Managing instructions</span>
<small>Register, review, approve, and verify active constraints.</small>
</a>

</div>
