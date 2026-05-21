# Managing instructions

<p className="craik-meta"><span>6 min read</span><span>Guide</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll do**

Register declared instruction sources, inspect distilled proposals,
approve or reject them with receipts, and verify that approved
constraints appear in case files and compiled prompts.

</div>

<div className="craik-keypoint">

**Keep discovery and authority separate.**

Registering a file makes it eligible for ingestion. It does not make
the file, or any extracted statement inside it, active runtime
authority.

</div>

## 1 · Register sources

Use canonical paths for standard source kinds and explicit project
paths for policy documents.

```sh
craik instructions register agents_md AGENTS.md --project my-project
craik instructions register codex_instructions .codex/instructions.md --project my-project
craik instructions register policy_doc docs/policies/release.md --project my-project
```

Craik confines every path to the registered project root. Standard
source kinds must use their canonical path; `policy_doc` sources can
use declared project policy paths.

## 2 · Ingest proposals

Ingestion refreshes snapshots, parses sources, attaches provenance,
categorizes statements, defers stale proposals, opens contradiction
reports, and creates inactive proposals.

```sh
craik instructions ingest --project my-project
```

Then inspect the resulting review queue:

```sh
craik instructions list --status proposed
craik instructions list --category security_rule
craik instructions show <item-id>
```

Review the statement, category, source ID, source path, line range,
snapshot status, and contradiction state before approving.

<div className="craik-grid">

<div><h4>Approve clear authority</h4><p>Use a short rationale that explains why the instruction should govern future runs.</p></div>
<div><h4>Reject noise</h4><p>Reject extracted text that is descriptive, stale, duplicate, or outside runtime scope.</p></div>
<div><h4>Defer conflict</h4><p>Resolve cross-source contradictions before making either side active.</p></div>
<div><h4>Recheck drift</h4><p>Changed or missing source snapshots invalidate earlier authority until reviewed again.</p></div>

</div>

## 3 · Approve or reject

```sh
craik instructions approve <item-id> --rationale "Matches the release policy"
craik instructions reject <item-id> --rationale "Descriptive note, not a runtime rule"
```

Approved proposals become governing constraints and receive promotion
reviews. Rejected proposals remain auditable but inactive.

Stale or contradicted items require an override:

```sh
craik instructions approve <item-id> \
  --override \
  --override-rationale "Maintainer accepted this policy during migration"
```

Use overrides sparingly. The review receipt records whether the
approval bypassed stale or contradiction guards. Approval receipts also
carry an integrity HMAC; constraints with missing or invalid receipt
HMACs are excluded from case files and compiled prompts.

## 4 · Verify runtime use

Build a case file and compile a prompt for a task that belongs to the
project.

```sh
craik case build <task-id>
craik prompt compile <task-id> --runner <runner-id>
```

The case file should include a deterministic `distillations` evidence
section for governing constraints. The compiled prompt should contain
exactly one `Active instruction constraints` section. Items render as:

```text
(policy) Follow the release approval policy. [instruction_source_agents_md @ AGENTS.md:3-3]
```

If no governing constraints exist, the section is still present with
an explicit empty state. Stale governing items are excluded and shown
as distillation warnings instead.

## 5 · Maintain the registry

Re-run source registration when a project adds or removes declared
instruction files. Re-run ingestion after source text changes, then
review deferred proposals before release work depends on them.

<div className="craik-keypoint">

**A clean queue is part of release readiness.**

Before cutting a release, inspect proposed, deferred, stale, and
contradicted items. Runtime prompts should not depend on unresolved
instruction ambiguity.

</div>

## What's next

<div className="craik-next">

<a href="../../reference/instruction-sources/">
<strong>Reference</strong>
<span>Instruction sources</span>
<small>Supported source kinds, canonical paths, and registry boundaries.</small>
</a>

<a href="../../reference/distilled-instructions/">
<strong>Reference</strong>
<span>Distilled instructions</span>
<small>Proposal states, categories, provenance, and snapshots.</small>
</a>

<a href="../../reference/instruction-approval/">
<strong>Reference</strong>
<span>Instruction approval</span>
<small>Review receipts, overrides, and active constraints.</small>
</a>

</div>
