# Quickstart

<p className="craik-meta"><span>10 min · hands-on</span><span>For first-time operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Install Craik, point it at a Git repository, build a case file, run policy
tests, and emit a handoff — without making a single live provider call.
Every output we discuss is real and persists on disk, so you can inspect
it after the run.

</div>

This tutorial uses the **fixture-backed provider path**, so it needs zero
credentials and zero network access. When you're done, the same project,
task, case file, receipts, and handoff can be re-run against live providers
by adding a credential profile and flipping policy.

## Start with the agent shell

Craik can now launch before setup is complete:

```bash title="First launch"
craik
```

The shell prints a readiness card instead of failing when operator auth,
provider credentials, or model selection are missing. Use it to discover
next actions, then drop back to subsystem commands whenever you want
stable JSON output.

```bash title="Readiness and one-shot mode"
craik status
craik -z "Summarize readiness."
```

## Before you start

- You completed [Installation](installation.md) (`craik --version` works).
- You have a Git repository handy. The Craik repo itself works fine if you
  don't have one.
- You're in a shell where `craik` resolves to the binary you just installed.

## 1 · Pin Craik's state to a sandbox

For the duration of this walkthrough, send all Craik state to a scratch
directory so you can blow it away cleanly at the end.

```bash title="Sandbox home"
export CRAIK_HOME=/tmp/craik-quickstart
craik home init
```

<div className="craik-keypoint">

**Why a sandbox?**

`CRAIK_HOME` decides where projects, receipts, handoffs, and case files
live. Pinning it to `/tmp/craik-quickstart` keeps this tutorial isolated
from your real `~/.craik/` directory. To start over: `rm -rf /tmp/craik-quickstart`.

</div>

## 2 · Register a project

Point Craik at a Git repository. This creates a **project profile** —
the runner-readable view Craik builds from your repo state, docs paths,
and policy posture.

```bash title="Register the current directory as a project"
craik project add . --name Example
craik project list
```

You should see `Example` in the listing, along with a project id like
`pid_xxxx`. Craik scanned the repo and noted conventional docs paths
(`README.md`, `docs/`) and immutable evidence paths
(`docs/adr/` if present).

:::note
Project registration only *reads* — it doesn't write back to your
repository. Everything lands in `$CRAIK_HOME/state/`.
:::

## 3 · Create a task

A **task** is a unit of work scoped by an objective and an intent lock. The
intent lock declares the boundaries the agent is allowed to act within.

```bash title="Create a docs-review task"
craik task create \
  --project Example \
  --title "Review docs" \
  --objective "Review documentation against implementation state." \
  --mode review \
  --out-of-scope "ADR edits"
```

Craik prints the new task id (something like `task_review_docs`) and the
matching intent lock id. The `--out-of-scope` flag tells future agents that
edits to ADR files are not permitted under this lock.

## 4 · Build a case file

The **case file** is the per-task pre-run brief — evidence, docs, immutable
paths, assumptions, stale-risk warnings, and a verification plan. The case
file is what an agent reads *before* it acts.

```bash title="Assemble the case file"
craik case build task_review_docs --no-github
craik case show task_review_docs
```

`craik case show` prints the structured JSON. Skim it once — you'll see:

- `evidence` references back to the repo, docs, immutable paths, and any
  GitHub state Craik was allowed to read.
- `assumptions` for context Craik *couldn't* find (for example, when no
  memory backend is configured).
- `stale_risk_markers` highlighting evidence that may have moved since it
  was indexed.
- `verification_plan` listing the validation steps the next runner should
  execute.

<div className="craik-keypoint">

**`--no-github`**

This flag keeps the case-file build offline. Drop it once you've configured
the GitHub adapter, and Craik will fold in open issues, PRs, and review
state as additional evidence.

</div>

## 5 · Run the policy gate

Before anything else, validate that the default policy envelope behaves the
way you expect:

```bash title="Exercise the policy contract"
craik policy test
```

The policy gate verifies strict defaults, immutable path behavior, memory
proposal defaults, fail-open receipt shape, automation fail-closed
behavior, and redaction. Every line that passes is a guarantee for the
runner that's about to consume the case file.

## 6 · Emit a handoff

When work ends — whether the agent finished, failed, or was interrupted —
Craik writes a **handoff**: a structured continuity record the next actor
can resume from.

```bash title="Create a handoff for the next agent"
craik handoff create task_review_docs \
  --summary "Reviewed docs and recorded current state." \
  --test-run "craik policy test" \
  --next-step "Review memory proposals."
```

Then render it as Markdown:

```bash title="Read the handoff as Markdown"
craik handoff show task_review_docs --markdown
```

The handoff captures the summary, the validation you ran, declared
next steps, and a self-audit checklist that flags whether redaction,
receipts, assumptions, and validation were reviewed.

## 7 · Try the full Stigmem demo

For an end-to-end walkthrough that adds contradiction detection, memory
proposals, receipts, work-graph export, *and* governed
provider-backed execution against deterministic fixtures, run the bundled
demo from a Stigmem checkout:

```bash title="The bundled demo — no credentials required"
craik demo stigmem-docs --repo-path . --no-github
```

The demo touches the entire MVP surface: project, task, case file,
contradiction, memory proposal, receipt, handoff, deterministic
OpenAI/Anthropic provider runs, and a work-graph export. No file edits.
No live model calls. This is also the command CI runs against every PR.

## 8 · Try the persistent agent demo

For the v0.9.0 persistent agent flow, run the deterministic launch demo
from any Git checkout:

```bash title="Persistent agent launch demo — no credentials required"
craik demo persistent-agent --repo-path .
```

The demo launches fixture-backed persistent sessions for OpenAI,
Anthropic, Gemini, and a local OpenAI-compatible preset, sends one
prompt through each session, records provider receipts, writes handoffs,
and inspects final session state. To keep the output shorter while
testing the hosted-provider happy path:

```bash title="Limit the persistent agent demo"
craik demo persistent-agent \
  --repo-path . \
  --provider-id provider_openai \
  --provider-id provider_anthropic
```

## What you produced

If you walked the full path above, your sandbox now contains:

<div className="craik-grid">

<div>
<h4><code>state/</code></h4>
<p>SQLite store with the <code>Example</code> project, <code>task_review_docs</code>, its case file, the intent lock, and the handoff.</p>
</div>

<div>
<h4><code>case-files/</code></h4>
<p>Exported case-file JSON — the same payload <code>craik case show</code> prints.</p>
</div>

<div>
<h4><code>handoffs/</code></h4>
<p>Structured handoff (JSON) and the Markdown rendering.</p>
</div>

<div>
<h4><code>receipts/</code></h4>
<p>Empty unless you wired live provider calls — receipts are written for every governed action.</p>
</div>

</div>

Inspect them with whatever you use day-to-day:

```bash
ls -la $CRAIK_HOME
sqlite3 $CRAIK_HOME/state/craik.sqlite ".tables"
```

## Cleanup

```bash title="Tear down the sandbox"
rm -rf /tmp/craik-quickstart
unset CRAIK_HOME
```

## What's next

<div className="craik-next">

<a href="../../concepts/project-model/">
<strong>Read</strong>
<span>The project model</span>
<small>Understand what a project profile actually contains and how agents consume it.</small>
</a>

<a href="../../concepts/case-files/">
<strong>Read</strong>
<span>How case files work</span>
<small>Evidence, assumptions, stale-risk markers, and the verification plan.</small>
</a>

<a href="../authentication/">
<strong>Step up</strong>
<span>Authenticate &amp; add credentials</span>
<small>OIDC login, credential profiles, pools, and workload identity for CI.</small>
</a>

</div>
