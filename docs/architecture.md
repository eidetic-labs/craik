# Architecture

<p className="craik-meta"><span>5 min read</span><span>For architects &amp; contributors</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll learn**

- The seven runtime layers Craik composes against.
- The flow a task moves through, from request to handoff.
- The patterns Craik borrows from adjacent runtimes — and what Craik
  adds on top.
- The core typed contracts that make the layers interchangeable.

</div>

<div className="craik-keypoint">

**Layered, separable, contract-bound.**

Craik is organized as a set of runtime layers. The layers should remain
separable so Craik can support different model providers, tool
environments, and memory backends without weakening the product thesis.

</div>

## Layers

<div className="craik-grid">

<div>
<h4>1 · Gateway</h4>
<p>Receives human and machine requests, normalizes them, creates runtime
tasks. Owns CLI / API / UI entry points, auth context, project
selection, the initial policy envelope, and event streaming.</p>
</div>

<div>
<h4>2 · Project model</h4>
<p>Builds the current working model for a task from repo state,
issues/PRs, docs, ADRs, recent handoffs, Stigmem facts, CI artifacts,
and user-provided instructions. Outputs the case file, constraints,
relevant facts, stale-risk warnings, contradiction warnings, and
verification plan.</p>
</div>

<div>
<h4>3 · Orchestration</h4>
<p>Decomposes work and coordinates agents — role selection, model
routing, task decomposition, parallel execution, specialist
assignment, review loops, interruption handling, stateful handoff
creation. Coordinates work; <em>does not</em> own truth.</p>
</div>

<div>
<h4>3a · Runner adapter</h4>
<p>Thin boundary between Craik contracts and concrete agent
environments. First-class adapters: Codex, Claude, Gemini. Adapters
translate case files into runner-specific context, pass policy
envelopes through, and translate runner-specific artifacts back into
Craik contracts.</p>
</div>

<div>
<h4>4 · Capability</h4>
<p>Exposes tools under explicit policy: file reads/writes, shell
commands, Git ops, GitHub ops, web search, package registries, CI
inspection, memory reads/writes, plugin execution. Each capability is
scoped, auditable, and revocable.</p>
</div>

<div>
<h4>5 · Memory</h4>
<p>Stores and retrieves durable state. Backends: ephemeral (tests),
local SQLite (single-user), Stigmem (real team use). Depends on
capabilities — facts, provenance, scopes, trust tiers, contradiction
tracking, federation, retention — not specific feature assumptions.</p>
</div>

<div>
<h4>6 · Work graph</h4>
<p>Connects runtime objects. Nodes: tasks, agents, handoffs, facts,
decisions, issues, PRs, branches, files, docs, ADRs, commands, tests,
CI runs, generated artifacts. Edges: <code>depends on</code>,
<code>created by</code>, <code>verified by</code>, <code>contradicts</code>,
<code>supersedes</code>, <code>implements</code>, <code>blocks</code>.</p>
</div>

<div>
<h4>7 · Experience</h4>
<p>Operator surfaces — CLI, repository dashboard, task detail view,
handoff viewer, contradiction inbox, work graph explorer, capability
receipt log. The runtime's read surface.</p>
</div>

</div>

## Terminal UI Strategy

Craik's terminal interface is an Experience-layer client of the Gateway, not
an execution backend. The production command still launches the maintained
legacy Textual runtime today, but new terminal UI development targets Rust and
Ratatui.

The Ratatui client should consume the Gateway JSONL event contract and render
the full provenance stream: model selection, assistant output, working state,
tool calls, file targets, shell commands, approvals, denials, receipts,
handoffs, and final run summaries. Provider-specific behavior belongs behind
the Gateway, runner adapters, and capability layers; the TUI should display
those events without owning provider execution.

## Runtime flow

A task moves through the layers in a deterministic sequence.

<ol className="craik-steps">
<li>A user or system creates a task.</li>
<li>Craik creates a policy envelope.</li>
<li>Craik assembles a project case file.</li>
<li>The orchestrator selects agent roles and work decomposition.</li>
<li>Agents execute with scoped capabilities.</li>
<li>Tool use creates receipts.</li>
<li>Agents produce artifacts and findings.</li>
<li>Craik verifies required checks.</li>
<li>Memory updates are proposed or written according to policy.</li>
<li>A structured handoff is created.</li>
<li>The work graph is updated.</li>
</ol>

## Borrowed patterns and Craik extensions

Adjacent agent runtimes have useful patterns. Craik adopts the ones
that serve a durable runtime and adds what's needed on top.

| Source pattern | Craik adoption | Craik extension |
| --- | --- | --- |
| Gateway runtime | CLI/API gateway ergonomics inform entry points and session routing. | Gateway also creates policy envelopes and receipt obligations. |
| Workspace runtime | Project profile and local runtime state isolate work. | Case files and handoffs make workspace state portable across agents. |
| Skills runtime | Skills provide repeatable operating guidance. | Skills declare context contracts and capability requirements. |
| Tool descriptors | Tools are discovered as typed capabilities. | Capabilities require grants and produce receipts. |
| Orchestrator | Orchestrator decomposes complex tasks. | Orchestrator uses Stigmem-backed project memory and cannot flatten unresolved contradictions. |
| Specialists | Workers receive scoped context and return typed results. | Worker results become graph-linked artifacts and durable handoffs. |
| Task board | Task state survives the active run. | Task state becomes part of a work graph connected to facts, PRs, receipts, and decisions. |
| Codex / Claude / Gemini runners | Direct adapters execute work in real agent environments. | Adapters normalize outputs into Craik contracts and memory proposals. |

## Core runtime contracts

Craik defines stable schemas so adapters, runners, and plugins can
integrate against the same product surface.

**The MVP contract set:** task requests · project case files · agent
role manifests · capability grants · capability receipts · handoffs ·
proposed facts · contradiction reports · verification results · work
graph events.

These contracts are more important than any single adapter language.
Craik core starts as a Python 3.12+ CLI runtime, while the contracts
remain the basis for interoperability with Codex, Claude, Gemini, local
agent runtimes, GitHub, CI, TypeScript gateways, UI surfaces, and
Stigmem.

## What's next

<div className="craik-next">

<a href="../runtime-contracts/">
<strong>Read next</strong>
<span>Runtime contracts</span>
<small>The typed shapes every layer speaks.</small>
</a>

<a href="../features/">
<strong>Read</strong>
<span>Features</span>
<small>Implementable feature surface across the seven layers.</small>
</a>

<a href="../concepts/project-model/">
<strong>Concept</strong>
<span>Project model</span>
<small>The foundational layer-2 object every other layer composes against.</small>
</a>

</div>
