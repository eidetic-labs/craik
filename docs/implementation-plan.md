# Implementation Plan

<p className="craik-meta"><span>14 min read</span><span>For contributors</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The buildable sequence that turns the Craik concept into a shipped
runtime: stack, repository shape, milestones with build / commands /
acceptance, the first end-to-end scenario, deferred decisions, and the
decided project defaults.

</div>

<div className="craik-keypoint">

**CLI-first, contract-first, test-first.**

Each milestone is a buildable slice with concrete commands and
acceptance criteria. A UI waits until the CLI workflow proves the
runtime contracts are correct.

</div>

## Accepted stack

<div className="craik-fields">

<div>
<dt>Choice</dt>
<dt><span className="craik-fields__type">Why</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Python 3.12+</dt>
<dt><span className="craik-fields__type">core</span></dt>
<dd>Stigmem already has Python surfaces; keeps Craik close to common agent-runtime conventions.</dd>
</div>

<div>
<dt>Typer</dt>
<dt><span className="craik-fields__type">CLI</span></dt>
<dd>Type-driven CLI with minimal boilerplate.</dd>
</div>

<div>
<dt>Pydantic</dt>
<dt><span className="craik-fields__type">contracts</span></dt>
<dd>Makes versioned contracts straightforward.</dd>
</div>

<div>
<dt>SQLite</dt>
<dt><span className="craik-fields__type">state</span></dt>
<dd>Enough for local task, receipt, handoff, and work-graph state.</dd>
</div>

<div>
<dt>stdlib HTTP</dt>
<dt><span className="craik-fields__type">first calls</span></dt>
<dd>For initial Stigmem and GitHub API calls.</dd>
</div>

<div>
<dt><code>pytest</code> · <code>ruff</code> · <code>mypy</code></dt>
<dt><span className="craik-fields__type">quality</span></dt>
<dd>Test and quality gates from day one.</dd>
</div>

</div>

<div className="craik-keypoint">

**Dependency posture.**

Favor reproducibility. Exact pins for runtime dependencies once
implementation begins; lockfile updates reviewed intentionally.
Optional provider, browser, UI, or adapter dependencies stay as extras
rather than core dependencies.

</div>

## Repository shape

Initial structure:

```text
craik/
  __init__.py
  cli.py
  contracts/
    task.py
    project.py
    policy.py
    case_file.py
    receipt.py
    handoff.py
    memory.py
    graph.py
    evidence.py
    assumption.py
    delegation.py
    intent.py
    instruction.py
    quality.py
    artifact.py
  runtime/
    project_registry.py
    paths.py
    case_assembler.py
    executor.py
    handoff_writer.py
    receipt_store.py
    policy_engine.py
    budget.py
    prompt_compiler.py
    critic.py
    distiller.py
  memory/
    base.py
    ephemeral.py
    local.py
    stigmem.py
  adapters/
    repo.py
    github.py
  runners/
    base.py
    codex.py
    claude.py
    gemini.py
  orchestration/
    roles.py
    orchestrator.py
    worker_result.py
  graph/
    store.py
    export.py
tests/
docs/
```

## Milestone 1 · Contract foundation

<div className="craik-grid">

<div><h4>Package skeleton</h4></div>
<div><h4>CLI skeleton</h4></div>
<div><h4>Pydantic models for core contracts</h4></div>
<div><h4>Schema version fields</h4></div>
<div><h4>JSON serialization / deserialization</h4></div>
<div><h4>Validation tests</h4></div>

</div>

**Commands:** <code>craik version</code> · <code>craik schema list</code> · <code>craik schema show &lt;name&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>All schemas validate sample fixtures.</li>
<li>Invalid fixtures produce clear errors.</li>
<li>Docs examples match real schemas.</li>
<li>CI runs lint, type, and test checks.</li>
</ol>

## Milestone 2 · Project registry and local state

<div className="craik-grid">

<div><h4>Craik home path resolver</h4></div>
<div><h4><code>CRAIK_HOME</code> override</h4></div>
<div><h4>Default <code>~/.craik</code> home</h4></div>
<div><h4>Structured home subdirectories</h4></div>
<div><h4>Secure permissions for home and secrets</h4></div>
<div><h4>SQLite local store</h4></div>
<div><h4>Project registry</h4></div>
<div><h4>Repo detection</h4></div>
<div><h4>Immutable path config</h4></div>
<div><h4>Local memory backend</h4></div>

</div>

**Commands:** <code>craik init</code> · <code>craik project add &lt;path&gt;</code> · <code>craik project list</code> · <code>craik project show &lt;id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Default home resolves to <code>~/.craik</code>.</li>
<li><code>CRAIK_HOME</code> overrides the default.</li>
<li><code>config</code>, <code>secrets</code>, <code>state</code>, <code>cache</code>, <code>logs</code>, <code>receipts</code>, <code>handoffs</code>, <code>case-files</code>, and <code>projects</code> directories are created as needed.</li>
<li>Secrets files are owner-readable/writable where supported.</li>
<li>Project-local <code>.craik/</code> is created only by explicit opt-in.</li>
<li>Project can be registered from a Git repo.</li>
<li>Registry persists between commands.</li>
<li>Project profile validates.</li>
<li>Immutable path policy is stored.</li>
</ol>

## Milestone 3 · Case-file assembly

<div className="craik-grid">

<div><h4>Repository adapter</h4></div>
<div><h4>Branch / diff inspection</h4></div>
<div><h4>Docs discovery</h4></div>
<div><h4>Default repository-context exclusions</h4><p>For generated, dependency, build, cache, archive-heavy paths.</p></div>
<div><h4>Project + user override rules</h4><p>For discovery include / exclude behavior.</p></div>
<div><h4>ADR / policy discovery</h4></div>
<div><h4>Stigmem / local fact loading</h4></div>
<div><h4>Stale-risk section</h4></div>
<div><h4>Evidence references</h4></div>
<div><h4>Assumption ledger</h4></div>
<div><h4>Context budget accounting</h4></div>
<div><h4>Context debt</h4><p>For paths skipped by defaults, overrides, or budget pressure.</p></div>
<div><h4>Verification-plan section</h4></div>
<div><h4>Markdown + JSON output</h4></div>

</div>

**Commands:** <code>craik task create --project &lt;id&gt; --title "..."</code> · <code>craik case build &lt;task-id&gt;</code> · <code>craik case show &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Case file includes repo status.</li>
<li>Docs and immutable paths are labeled.</li>
<li>Generated and dependency paths are excluded by default unless explicitly included.</li>
<li>Project and user overrides can extend, replace, or explicitly include paths from the default discovery rules.</li>
<li>Excluded paths are visible in case-file context metadata rather than silently disappearing.</li>
<li>Facts include source / confidence.</li>
<li>Unsupported conclusions are tracked as assumptions.</li>
<li>Included and omitted context is explainable.</li>
<li>Output is deterministic for fixtures.</li>
<li>Missing context is clearly reported.</li>
</ol>

## Milestone 4 · Policy and receipts

<div className="craik-grid">

<div><h4>Policy envelope generation</h4></div>
<div><h4>Strict / trusted-local / automation profiles</h4></div>
<div><h4>Explicit fail-open profile handling</h4></div>
<div><h4>Capability grant model</h4></div>
<div><h4>Immutable path protection</h4></div>
<div><h4>Central redaction utility</h4></div>
<div><h4>Receipt store</h4></div>
<div><h4>Policy denial receipts</h4></div>
<div><h4>Shell-command receipt wrapper</h4></div>
<div><h4>File-write receipt wrapper</h4></div>

</div>

**Commands:** <code>craik policy show &lt;task-id&gt;</code> · <code>craik receipts list &lt;task-id&gt;</code> · <code>craik receipts show &lt;receipt-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Strict mode is default.</li>
<li>Fail-open is available only through named policy profiles.</li>
<li>Denied writes are blocked.</li>
<li>Allowed actions create receipts.</li>
<li>Fail-open decisions create receipts.</li>
<li>Receipts are redacted before persistence.</li>
<li>Shell-command results are summarized.</li>
<li>Receipts link back to task and policy envelope.</li>
</ol>

## Milestone 5 · Handoff loop

<div className="craik-grid">

<div><h4>Structured handoff writer</h4></div>
<div><h4>Markdown handoff writer</h4></div>
<div><h4>Handoff validation</h4></div>
<div><h4>Handoff load into case file</h4></div>
<div><h4>Memory proposal attachment</h4></div>

</div>

**Commands:** <code>craik handoff create &lt;task-id&gt;</code> · <code>craik handoff show &lt;task-id&gt;</code> · <code>craik handoff list --project &lt;id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Every completed task can produce a handoff.</li>
<li>Handoff includes receipts.</li>
<li>Handoff includes verification state.</li>
<li>Handoff is loaded into the next related case file.</li>
<li>Handoff schema validates.</li>
</ol>

## Milestone 6 · Stigmem backend

<div className="craik-grid">

<div><h4>Stigmem config</h4></div>
<div><h4>API key setup</h4></div>
<div><h4>Backend capability detection</h4></div>
<div><h4>Fact search / read / write</h4></div>
<div><h4>Fact proposal mapping</h4></div>
<div><h4>Provenance reads</h4></div>
<div><h4>Optional recall support</h4></div>
<div><h4>Optional conflict support</h4></div>
<div><h4>Handoff summary fact writes</h4></div>
<div><h4>Memory diff for task runs</h4></div>

</div>

**Commands:** <code>craik connect stigmem --url &lt;url&gt;</code> · <code>craik memory search &lt;query&gt;</code> · <code>craik memory propose &lt;task-id&gt;</code> · <code>craik memory diff &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Craik can connect to a local Stigmem node.</li>
<li>Backend verifies <code>GET /healthz</code> and <code>GET /.well-known/stigmem</code>.</li>
<li>Failed auth has a clear error.</li>
<li>Facts are included in case files.</li>
<li>Direct fact writes require memory-write grant.</li>
<li>Proposed facts can be reviewed before write.</li>
<li>Written facts include provenance.</li>
<li>Optional recall / conflict capabilities are detected without becoming required.</li>
<li>Craik falls back to local proposals, local contradiction reports, and local memory diffs when optional Stigmem capabilities are unavailable.</li>
</ol>

## Milestone 7 · GitHub adapter

<div className="craik-grid">

<div><h4>GitHub auth detection</h4></div>
<div><h4>Repo mapping</h4></div>
<div><h4>Issue / PR reads</h4></div>
<div><h4>Changed-file reads</h4></div>
<div><h4>Check-status reads</h4></div>
<div><h4>Guarded issue / PR / comment writes</h4></div>

</div>

**Commands:** <code>craik github status &lt;project-id&gt;</code> · <code>craik github issues &lt;project-id&gt;</code> · <code>craik github prs &lt;project-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Case file includes relevant GitHub state.</li>
<li>GitHub writes require grants.</li>
<li>Created links appear in handoff.</li>
<li>Unauthenticated mode remains usable for local-only tasks.</li>
</ol>

## Milestone 8 · Work graph

<div className="craik-grid">

<div><h4>Graph node / event models</h4></div>
<div><h4>Graph store</h4></div>
<div><h4>Export command</h4></div>
<div><h4>Task / handoff / fact / receipt graph links</h4></div>
<div><h4>Contradiction graph links</h4></div>
<div><h4>Human delegation-point nodes</h4></div>

</div>

**Commands:** <code>craik graph export &lt;project-id&gt;</code> · <code>craik graph show-task &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Each task creates graph nodes.</li>
<li>Handoffs and receipts are linked.</li>
<li>Fact proposals link to evidence.</li>
<li>Graph export is deterministic.</li>
</ol>

## Milestone 8a · Evidence, assumptions, and onboarding

<div className="craik-grid">

<div><h4>Evidence reference model</h4></div>
<div><h4>Assumption ledger model</h4></div>
<div><h4>Belief promotion lifecycle model</h4></div>
<div><h4>Onboarding command</h4></div>
<div><h4>Context budgeting metadata</h4></div>
<div><h4>Provenance-aware documentation links</h4></div>
<div><h4>Decision-record suggestion hooks</h4></div>

</div>

**Commands:** <code>craik onboard --project &lt;project-id&gt;</code> · <code>craik assumptions list &lt;task-id&gt;</code> · <code>craik evidence show &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Case files explain included and omitted context.</li>
<li>Assumptions are separate from facts.</li>
<li>Memory proposals require evidence before promotion.</li>
<li>Onboarding output includes policies, recent handoffs, contradictions, stale-risk warnings, and allowed next actions.</li>
<li>Decision-record suggestions are generated only as proposals.</li>
</ol>

## Milestone 8b · Policy tests, delegation, and budgets

<div className="craik-grid">

<div><h4>Policy fixture test harness</h4></div>
<div><h4>Required policy regression tests</h4></div>
<div><h4>Human delegation-point model</h4></div>
<div><h4>Budget and quota model</h4></div>
<div><h4>Budget receipts</h4></div>
<div><h4>Budget enforcement hooks</h4></div>

</div>

**Commands:** <code>craik policy test</code> · <code>craik delegations list</code> · <code>craik budgets show &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Policy tests cover immutable paths, memory-proposal defaults, fail-open receipts, automation fail-closed behavior, runner grant boundaries, and redaction.</li>
<li>Unresolved delegation points appear in handoffs.</li>
<li>Resolved delegation points create receipts.</li>
<li>Budgets appear in case files and receipts.</li>
<li>Budget exhaustion blocks or escalates according to policy.</li>
</ol>

## Milestone 8c · Instruction distillation and runtime quality

<div className="craik-grid">

<div><h4>Runtime instruction source registry</h4><p>Receipted registration records declared sources before ingestion or promotion.</p></div>
<div><h4>Markdown instruction distiller</h4><p>Parses registered instruction files into deterministic statement candidates without store writes.</p></div>
<div><h4>Source hash tracking</h4><p>Refreshes active registered sources from real repo files, stores newline-normalized SHA-256 snapshots, and marks changed or missing sources for stale invalidation.</p></div>
<div><h4>Line/range provenance</h4><p>Persists one deterministic provenance record per parsed statement with source snapshot, line and column range, summary, and excerpt hash.</p></div>
<div><h4>Distillation proposal store</h4><p>Categorizes provenanced statements with deterministic rules and writes reviewable proposals while surfacing unclassified candidates.</p></div>
<div><h4>Inter-source contradictions</h4><p>Normalizes proposal triples across sources and opens contradiction reports for diverging policy, boundary, command, instruction, and security-rule guidance.</p></div>
<div><h4>Operator approval flow</h4><p>Requires explicit operator approval or denial receipts before proposals become governing runtime constraints.</p></div>
<div><h4>Task intent lock</h4></div>
<div><h4>Expiring scratchpad</h4></div>
<div><h4>Scope-change proposal model</h4></div>
<div><h4>Self-audit checklist</h4></div>
<div><h4>Runtime critic</h4></div>
<div><h4>Evidence coverage score</h4></div>
<div><h4>Handoff quality score</h4></div>
<div><h4>Tool-result attestation</h4></div>
<div><h4>Memory-impact preview</h4></div>

</div>

**Commands:** <code>craik instructions scan &lt;project-id&gt;</code> · <code>craik instructions distill &lt;project-id&gt;</code> · <code>craik intent show &lt;task-id&gt;</code> · <code>craik scratchpad list &lt;task-id&gt;</code> · <code>craik quality check &lt;task-id&gt;</code> · <code>craik memory preview &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Instruction distillation uses declared sources only.</li>
<li>Every extracted statement has stable provenance linked to the source snapshot.</li>
<li>Categorized distillation proposals are deterministic and report unclassified candidates.</li>
<li>Inter-source conflicts surface as contradiction reports and defer conflicted proposals.</li>
<li>Only explicitly approved governing instructions are visible to runtime consumers.</li>
<li>Source-hash changes invalidate stale distillations.</li>
<li>Extracted instruction facts remain proposals until approved.</li>
<li>Intent lock is included in case files and handoffs.</li>
<li>Scratchpad does not become durable memory without promotion.</li>
<li>Quality gates flag unsupported claims and missing validation.</li>
<li>Memory-impact preview appears before direct Stigmem writes.</li>
</ol>

## Milestone 8d · Runner intelligence and continuity

<div className="craik-grid">

<div><h4>Runner capability matrix</h4></div>
<div><h4>Agent workload memory</h4></div>
<div><h4>Known traps registry</h4></div>
<div><h4>Evidence expiration rules</h4></div>
<div><h4>Knowledge-freshness probes</h4></div>
<div><h4>Policy-aware prompt compiler</h4></div>
<div><h4>Real-runner contract test harness</h4></div>
<div><h4>Work-product classification</h4></div>
<div><h4>"What changed since last time" deltas</h4></div>
<div><h4>Recovery mode</h4></div>
<div><h4>Red-team mode</h4></div>

</div>

**Commands:** <code>craik runners matrix</code> · <code>craik traps list &lt;project-id&gt;</code> · <code>craik freshness probe &lt;task-id&gt;</code> · <code>craik prompt compile &lt;task-id&gt; --runner &lt;runner&gt;</code> · <code>craik recover &lt;task-id&gt;</code> · <code>craik delta &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Case files include known traps and freshness state.</li>
<li>Prompt compilation uses policy, context contracts, runner capabilities, and output schemas.</li>
<li>Recovery mode can resume from partial receipts, scratchpad, changed files, and unfinished handoff.</li>
<li>Real-runner contract tests validate adapter output shape.</li>
<li>Red-team mode can be required by policy.</li>
<li>Task starts can show relevant deltas since the last related run.</li>
</ol>

## Milestone 9 · Contradictions and memory diff

<div className="craik-grid">

<div><h4>Contradiction report model</h4></div>
<div><h4>Contradiction store</h4></div>
<div><h4>Contradiction list / show / resolve</h4></div>
<div><h4>Memory diff command</h4></div>
<div><h4>Resolution-to-memory-proposal flow</h4></div>

</div>

**Commands:** <code>craik contradictions list</code> · <code>craik contradictions show &lt;id&gt;</code> · <code>craik contradictions resolve &lt;id&gt;</code> · <code>craik memory diff &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Contradictions can be opened by an agent or user.</li>
<li>Contradictions are not overwritten by later facts.</li>
<li>Resolutions record rationale.</li>
<li>Memory diff includes contradiction state.</li>
</ol>

## Milestone 10 · Single-agent execution loop

<div className="craik-keypoint">

**Build after runner contracts and the durable single-agent state model are stable.**

</div>

<div className="craik-grid">

<div><h4>Task-run state machine</h4></div>
<div><h4>Run id and status model</h4></div>
<div><h4>Plan / act / observe / evaluate / continue / stop phases</h4></div>
<div><h4>Runner step contract</h4></div>
<div><h4>Max-iteration limit</h4></div>
<div><h4>Timeout and budget checks</h4></div>
<div><h4>Intent-lock stop-condition enforcement</h4></div>
<div><h4>Approval and grant checks before side effects</h4></div>
<div><h4>Step receipts</h4></div>
<div><h4>Observed-output capture</h4></div>
<div><h4>Memory proposal hooks</h4></div>
<div><h4>Handoff on completion / block / failure / interruption</h4></div>
<div><h4>Run resume</h4></div>
<div><h4>Run recovery</h4></div>
<div><h4>Agent exit discipline</h4></div>

</div>

**Commands:** <code>craik task run &lt;task-id&gt; --runner &lt;runner&gt;</code> · <code>craik runs show &lt;run-id&gt;</code> · <code>craik runs resume &lt;run-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Craik, not the chat transcript, owns the loop boundary.</li>
<li>Every side-effecting step checks policy before execution.</li>
<li>Each important step can produce a receipt.</li>
<li>Stop conditions halt the run before scope drift.</li>
<li>Iteration, budget, and timeout limits are enforced.</li>
<li>Interrupted runs can resume from persisted state.</li>
<li>Blocked or failed runs produce handoffs.</li>
<li>Memory updates remain proposals unless policy grants direct writes.</li>
</ol>

## Milestone 11 · Multi-agent orchestration

<div className="craik-keypoint">

**Build after the single-agent durable loop works.**

</div>

<div className="craik-grid">

<div><h4>Role manifests</h4></div>
<div><h4>Orchestrator task decomposition</h4></div>
<div><h4>Child task creation</h4></div>
<div><h4>Worker-result validation</h4></div>
<div><h4>Specialist handoffs</h4></div>
<div><h4>Parent handoff merge</h4></div>
<div><h4>Parallel read-only execution</h4></div>

</div>

**Commands:** <code>craik roles list</code> · <code>craik task split &lt;task-id&gt;</code> · <code>craik task run --multi-agent &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Specialists receive scoped case files.</li>
<li>Worker results validate.</li>
<li>Child handoffs link to parent.</li>
<li>Read-only work can run in parallel.</li>
<li>Unresolved contradictions block flattening into a final answer.</li>
</ol>

## Milestone 12 · First-class runner adapters

<div className="craik-grid">

<div><h4>Runner adapter interface</h4></div>
<div><h4>Codex adapter</h4></div>
<div><h4>Claude adapter</h4></div>
<div><h4>Gemini adapter</h4></div>
<div><h4>Runner metadata capture</h4></div>
<div><h4>Worker-result normalization</h4></div>
<div><h4>Handoff normalization</h4></div>
<div><h4>Memory-proposal normalization</h4></div>
<div><h4>Failure / block reporting</h4></div>

</div>

**Commands:** <code>craik runners list</code> · <code>craik runners inspect &lt;runner&gt;</code> · <code>craik task run --runner codex &lt;task-id&gt;</code> · <code>craik task run --runner claude &lt;task-id&gt;</code> · <code>craik task run --runner gemini &lt;task-id&gt;</code>

**Acceptance:**

<ol className="craik-steps">
<li>Codex, Claude, and Gemini adapters implement the same interface.</li>
<li>Each adapter consumes case files and policy envelopes.</li>
<li>Each adapter emits typed worker results or clear block / failure states.</li>
<li>Adapter outputs can create handoffs and receipts.</li>
<li>Runner-specific metadata is preserved without polluting core contracts.</li>
<li>Adjacent runtime bridges remain future integrations rather than required execution layers.</li>
</ol>

## Milestone 13 · Skills and probationary plugins

<div className="craik-grid">

<div><h4>Skill directory discovery</h4></div>
<div><h4>Project-scoped skills</h4></div>
<div><h4>Global skills</h4></div>
<div><h4>Context-contract declarations</h4></div>
<div><h4>Plugin descriptor model</h4></div>
<div><h4>Probationary plugin policy</h4></div>
<div><h4>Plugin receipt requirements</h4></div>

</div>

**Acceptance:**

<ol className="craik-steps">
<li>Skills alter case-file guidance without changing code.</li>
<li>Project skills override global skills.</li>
<li>Plugins expose typed capabilities.</li>
<li>Probationary plugins have limited grants.</li>
<li>Plugin use appears in receipts.</li>
</ol>

## First end-to-end scenario

The MVP target scenario — automated as a fixture-driven integration
test before broadening the platform.

<ol className="craik-steps">
<li>Register <code>eidetic-labs/stigmem</code> as the first demo project.</li>
<li>Connect to local Stigmem.</li>
<li>Create a docs-reconciliation task.</li>
<li>Build a case file from repo docs, ADRs, facts, and GitHub state.</li>
<li>Run a governed agent with docs-write capability.</li>
<li>Capture receipts for file writes and validation commands.</li>
<li>Generate a handoff.</li>
<li>Propose or write facts about the new state.</li>
<li>Export work graph for the task.</li>
</ol>

**The scenario explicitly validates:**

<ol className="craik-steps">
<li>ADRs are treated as immutable inputs.</li>
<li>Public docs do not receive internal-only labels or implementation tracking terms.</li>
<li>Stale docs are identified with evidence.</li>
<li>Stigmem facts are used as context with provenance.</li>
<li>Memory writes are proposed or written according to policy.</li>
<li>The final handoff can seed a follow-up task.</li>
</ol>

## Deferred decisions

These should be decided before coding starts, but they should not
block the planning docs.

<div className="craik-grid">

<div><h4>Hosted service posture</h4></div>
<div><h4>Relationship to existing Eidetic auth</h4></div>
<div><h4>Whether the first UI is built into Craik or kept separate</h4></div>

</div>

## Decided project defaults

<div className="craik-fields">

<div>
<dt>Decision</dt>
<dt><span className="craik-fields__type">Value</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>License</dt>
<dt><span className="craik-fields__type">MIT</span></dt>
<dd>Code reuse only — governance, contribution terms, and trademark covered separately.</dd>
</div>

<div>
<dt>Public repository</dt>
<dt><span className="craik-fields__type">GitHub</span></dt>
<dd><code>eidetic-labs/craik</code></dd>
</div>

<div>
<dt>Product framing</dt>
<dt><span className="craik-fields__type">framing</span></dt>
<dd>Durable agent runtime.</dd>
</div>

<div>
<dt>Reference memory substrate</dt>
<dt><span className="craik-fields__type">substrate</span></dt>
<dd>Stigmem.</dd>
</div>

<div>
<dt>Min Stigmem compatibility</dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Health · well-known metadata · authenticated fact read/write/query · fact provenance · scopes · confidence · source fields.</dd>
</div>

<div>
<dt>Initial interface</dt>
<dt><span className="craik-fields__type">surface</span></dt>
<dd>CLI-first.</dd>
</div>

<div>
<dt>First demo target</dt>
<dt><span className="craik-fields__type">scenario</span></dt>
<dd>Stigmem documentation and state reconciliation.</dd>
</div>

<div>
<dt>Initial first-class runners</dt>
<dt><span className="craik-fields__type">runners</span></dt>
<dd>Codex · Claude · Gemini.</dd>
</div>

<div>
<dt>Adjacent runtime relationship</dt>
<dt><span className="craik-fields__type">posture</span></dt>
<dd>Design reference and possible future bridge — not a required dependency.</dd>
</div>

<div>
<dt>Differentiator objective</dt>
<dt><span className="craik-fields__type">posture</span></dt>
<dd>Evidence-first, assumption-aware, policy-tested, budgeted, human-delegable agent work.</dd>
</div>

<div>
<dt>Core language</dt>
<dt><span className="craik-fields__type">language</span></dt>
<dd>Python 3.12+.</dd>
</div>

<div>
<dt>PyPI distribution</dt>
<dt><span className="craik-fields__type">package</span></dt>
<dd><code>craik</code></dd>
</div>

<div>
<dt>Python module</dt>
<dt><span className="craik-fields__type">module</span></dt>
<dd><code>craik</code></dd>
</div>

<div>
<dt>CLI command</dt>
<dt><span className="craik-fields__type">command</span></dt>
<dd><code>craik</code></dd>
</div>

<div>
<dt>Future npm package</dt>
<dt><span className="craik-fields__type">reserved</span></dt>
<dd><code>craik</code> (if needed).</dd>
</div>

<div>
<dt>Default local home</dt>
<dt><span className="craik-fields__type">path</span></dt>
<dd><code>~/.craik</code></dd>
</div>

<div>
<dt>Local home override</dt>
<dt><span className="craik-fields__type">env</span></dt>
<dd><code>CRAIK_HOME</code></dd>
</div>

<div>
<dt>Project-local metadata</dt>
<dt><span className="craik-fields__type">posture</span></dt>
<dd>Opt-in only.</dd>
</div>

<div>
<dt>Default policy profile</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Strict.</dd>
</div>

<div>
<dt>Fail-open behavior</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Allowed only through explicit named policy profiles.</dd>
</div>

<div>
<dt>Trusted-local profile</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Opt-in fail-open with mandatory receipts.</dd>
</div>

<div>
<dt>Automation profile</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Fail-closed.</dd>
</div>

<div>
<dt>Memory writes</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Proposals by default.</dd>
</div>

<div>
<dt>Secrets storage</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd><code>~/.craik/secrets/</code> or env vars · redacted before persistence.</dd>
</div>

<div>
<dt>Initial CLI framework</dt>
<dt><span className="craik-fields__type">tool</span></dt>
<dd>Typer.</dd>
</div>

<div>
<dt>Contract validation</dt>
<dt><span className="craik-fields__type">tool</span></dt>
<dd>Pydantic.</dd>
</div>

<div>
<dt>Local state</dt>
<dt><span className="craik-fields__type">tool</span></dt>
<dd>SQLite.</dd>
</div>

<div>
<dt>API client</dt>
<dt><span className="craik-fields__type">tool</span></dt>
<dd><code>httpx</code>.</dd>
</div>

<div>
<dt>Test &amp; quality gates</dt>
<dt><span className="craik-fields__type">tool</span></dt>
<dd><code>pytest</code> · <code>ruff</code> · <code>mypy</code>.</dd>
</div>

</div>

<div className="craik-keypoint">

**Name availability snapshot.**

Live registry checks on 2026-05-15 returned 404 for both
`https://pypi.org/pypi/craik/json` and
`https://registry.npmjs.org/craik` — the names appeared available at
that time. Publish early once package metadata is ready. If the plain
distribution name is lost before publication, fall back to
`craik-runtime` while preserving `craik` for the module and CLI command.

</div>

## Contribution and trademark follow-up

MIT governs code reuse but not project governance, contribution terms,
or trademark rights. Initial lightweight governance lives in
root-level policy files.

<div className="craik-fields">

<div>
<dt>Standard</dt>
<dt><span className="craik-fields__type">File</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Contribution guide</dt>
<dt><span className="craik-fields__type">file</span></dt>
<dd><code>CONTRIBUTING.md</code></dd>
</div>

<div>
<dt>Contribution certification</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>DCO, not CLA.</dd>
</div>

<div>
<dt>Code of conduct</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>Contributor Covenant 2.1 baseline.</dd>
</div>

<div>
<dt>Security disclosure</dt>
<dt><span className="craik-fields__type">file</span></dt>
<dd>Private report path in <code>SECURITY.md</code>.</dd>
</div>

<div>
<dt>Trademark guidance</dt>
<dt><span className="craik-fields__type">file</span></dt>
<dd><code>TRADEMARKS.md</code></dd>
</div>

<div>
<dt>Maintainer &amp; release policy</dt>
<dt><span className="craik-fields__type">file</span></dt>
<dd><code>MAINTAINERS.md</code></dd>
</div>

</div>

**Before broad external contribution, revisit:** final security
contact · DCO enforcement automation · release automation · package
publishing ownership · whether a dedicated governance document is
needed after `0.1.0`.

## What's next

<div className="craik-next">

<a href="../mvp/">
<strong>Read</strong>
<span>MVP plan</span>
<small>The accepted v0.x.0 scope and proof workflow.</small>
</a>

<a href="../mvp-roadmap/">
<strong>Read</strong>
<span>MVP roadmap</span>
<small>The release-readiness checklist driving v0.x.</small>
</a>

<a href="../runtime-contracts/">
<strong>Read</strong>
<span>Runtime contracts</span>
<small>The persisted contract shapes these milestones build against.</small>
</a>

</div>
