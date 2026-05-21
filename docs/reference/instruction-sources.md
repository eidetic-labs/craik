# Instruction sources

<p className="craik-meta"><span>4 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The registry, hash state, provenance, categories, stale invalidation,
conflict handling, and promotion rules that turn declared instruction
files into runtime constraints.

</div>

<div className="craik-keypoint">

**Not every Markdown file is authority.**

Craik does not treat raw instruction files as runtime authority.
Sources declare candidate evidence; promotion is a separate gate.

</div>

## Supported sources

| Kind | Path |
| --- | --- |
| `agents_md` | `AGENTS.md` |
| `claude_md` | `CLAUDE.md` |
| `gemini_md` | `GEMINI.md` |
| `hermes_md` | `HERMES.md` |
| `skills_md` | `SKILLS.md` |
| `cursor_rules` | `.cursorrules` |
| `github_copilot_instructions` | `.github/copilot-instructions.md` |
| `codex_instructions` | `.codex/instructions.md` |
| `policy_doc` | Explicitly declared project policy doc path |

Standard source kinds must use their canonical path. `policy_doc`
sources declare their own path and must be listed in the registry's
`declared_policy_doc_paths`.

<div className="craik-keypoint">

**Declared paths stay inside the project.**

Instruction ingestion resolves every source path under the registered
project root and rejects paths that escape it. Standard Markdown-shaped
sources emit one candidate per bullet outside fenced code blocks.
Declared policy documents are captured as one free-form statement block
so policy prose keeps its review context.

</div>

## Detection order

Craik never scans arbitrary Markdown as authority. A source becomes
eligible only after registration, and downstream ingestion follows the
registered source list in deterministic order:

<ol className="craik-steps">
<li>Canonical root instruction files: <code>AGENTS.md</code>, <code>CLAUDE.md</code>, <code>GEMINI.md</code>, <code>HERMES.md</code>, <code>SKILLS.md</code>.</li>
<li>Tool-specific instruction files: <code>.cursorrules</code>, <code>.github/copilot-instructions.md</code>, <code>.codex/instructions.md</code>.</li>
<li>Explicitly declared <code>policy_doc</code> paths in registry order.</li>
</ol>

Within a project, the runtime registry stores active sources in stable
kind/path order so repeated registration and ingestion passes produce
predictable downstream records.

## Registry boundaries

`craik.instruction_source_registry` is project-scoped. It records
declared sources, active source IDs, and policy doc paths. Active
source IDs must refer to registered active sources.

<div className="craik-keypoint">

**Discovery, not approval.**

The registry is a discovery boundary, not an approval boundary. Later
distillation and promotion steps must still preserve provenance,
stale-source state, contradiction reports, and human approval before
extracted instructions become active runtime constraints.

</div>

Registration is a receipted discovery action. The runtime
`register_source` API writes four records:

<div className="craik-grid">

<div><h4><code>craik.instruction_source</code></h4><p>The current declared source entry used by ingestion.</p></div>
<div><h4><code>craik.instruction_source_registration</code></h4><p>The immutable registration event with owner, actor, path, trust boundary, and optional content hash.</p></div>
<div><h4><code>craik.instruction_registry_receipt</code></h4><p>The audit record proving the registration action completed.</p></div>
<div><h4><code>craik.instruction_source_registry</code></h4><p>The project-level registry containing active source IDs and policy document paths.</p></div>

</div>

## Hash state and provenance

`craik.instruction_source_snapshot` records observed source identity
with a `sha256` content hash when the source is present.

<div className="craik-fields">

<div>
<dt>Hash status</dt>
<dt><span className="craik-fields__type">Meaning</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>unchanged</code></dt>
<dt><span className="craik-fields__type">stable</span></dt>
<dd>Observed hash matches the previous known state.</dd>
</div>

<div>
<dt><code>changed</code></dt>
<dt><span className="craik-fields__type">drift</span></dt>
<dd>Source exists and differs from the previous known state.</dd>
</div>

<div>
<dt><code>missing</code></dt>
<dt><span className="craik-fields__type">gone</span></dt>
<dd>Declared source was not found · must not include a content hash.</dd>
</div>

<div>
<dt><code>new</code></dt>
<dt><span className="craik-fields__type">first time</span></dt>
<dd>Source exists but has no previous known state.</dd>
</div>

</div>

`craik.instruction_provenance` links distilled material back to a
source and optional snapshot. Provenance uses a precise line range
when available or a source-level fallback when the extractor cannot
identify stable lines. **Partial line ranges are invalid** because
they make review ambiguous.

## Distilled instruction categories

| Category | Meaning |
| --- | --- |
| `instruction` | General runtime guidance for agents. |
| `policy` | Governance, approval, or authority requirement. |
| `preference` | Stable user, team, or project preference. |
| `command` | Command or validation instruction. |
| `boundary` | Scope, ownership, or authority boundary. |
| `handoff_rule` | Requirement for durable handoff content or timing. |
| `memory_rule` | Rule for memory reads, writes, proposals, or promotion. |
| `security_rule` | Security, secret, or safety-sensitive requirement. |
| `stale_risk` | Warning that prior context may become stale or unsafe. |

<div className="craik-keypoint">

**Policy and security-rule proposals require evidence.**

In addition to provenance. Approved proposals must include a promoted
constraint ID plus reviewer and decision time. Rejected and deferred
proposals also preserve reviewer and decision time.

</div>

## Stale invalidation

Snapshots are compared by source ID and content hash. Distillations
are deferred when their source changes, goes missing, is newly
discovered, or is omitted from the current scan. Deferral preserves
the proposal, provenance, evidence, and previous review decision for
audit, but the proposal is excluded from automatic promotion until it
is reviewed again.

Case files and onboarding reports surface stale instruction warnings
so agents do not treat outdated distilled instructions as active
constraints.

## Instruction conflicts

<div className="craik-decision">

<div>
<h4>Open a contradiction report</h4>
<p>Incompatible <code>instruction</code> · <code>policy</code> · <code>command</code> · <code>boundary</code> · <code>security_rule</code> proposals. Reports link conflicting proposal IDs, source IDs, and provenance IDs.</p>
</div>

<div>
<h4>Keep as reviewable disagreement</h4>
<p><code>preference</code> and <code>stale_risk</code> disagreements stay as reviewable proposals — they may represent tolerable local variation, not mutually exclusive authority.</p>
</div>

</div>

Conflicting proposals are deferred and excluded from automatic
promotion until the contradiction is reviewed.

## Promotion reviews

`craik.instruction_promotion_review` records approved, rejected, and
deferred promotion decisions. Reviews link policy envelopes, receipts,
memory proposals, and handoffs.

Approved reviews create `craik.promoted_instruction_constraint`
records. Active constraints retain proposal ID · source ID · source
snapshot ID · provenance IDs · evidence IDs · review links.

<div className="craik-keypoint">

**Only approved, non-contradicted constraints are consumed.**

Proposed, rejected, deferred, stale, or contradicted distillations
remain visible for review but inactive.

</div>

## Runtime consumption

<div className="craik-grid">

<div><h4>Case files</h4><p>Include active constraints in <code>context_budget.active_instruction_constraints</code>.</p></div>
<div><h4>Prompts</h4><p>Compilation renders constraints in the context section.</p></div>
<div><h4>Onboarding</h4><p>Reports include active instruction summaries in the project model.</p></div>
<div><h4>Handoffs</h4><p>Carry active constraint IDs forward as context debt.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../instruction-distillation-workflow/">
<strong>Reference</strong>
<span>Instruction distillation workflow</span>
<small>The 9-step pipeline these contracts feed.</small>
</a>

<a href="../instruction-distillation-view/">
<strong>Reference</strong>
<span>Instruction distillation view</span>
<small>The operator surface that audits proposals.</small>
</a>

<a href="../schemas/">
<strong>Reference</strong>
<span>Schema reference</span>
<small>All instruction-related contract shapes.</small>
</a>

</div>
