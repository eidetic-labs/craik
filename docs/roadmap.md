# Roadmap

<p className="craik-meta"><span>20 min read</span><span>For maintainers &amp; integrators</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The full Craik roadmap: rules every roadmap item must satisfy, the
documentation model, the release-gate sequence from v0.1.0 through
v0.12.0 (plus a post-MVP stability gate), and the 24 executable
workstreams that turn those gates into shippable PRs.

</div>

<div className="craik-keypoint">

**Executable by design.**

Every roadmap item must produce implementation, tests or validation,
and documentation. Craik should not ship features that only exist as
code or only exist as strategy. The smallest useful runtime ships
first; everything else builds on top.

</div>

## Roadmap rules

<ol className="craik-steps">
<li><strong>Every feature has docs.</strong> User-facing behavior requires guide docs · runtime contracts require reference docs · policy behavior requires security/governance docs · adapter behavior requires integration docs.</li>
<li><strong>Docs ship with implementation.</strong> A feature is not done until its docs, examples, and validation guidance are merged.</li>
<li><strong>Strict by default.</strong> New capabilities must respect policy envelopes, grants, redaction, receipts, and memory-write defaults.</li>
<li><strong>Evidence before memory.</strong> No durable assertion or Stigmem write without evidence, provenance, and scope.</li>
<li><strong>Source remains canonical.</strong> Derived memory, distilled instructions, generated docs, and summaries must cite source artifacts.</li>
<li><strong>CLI first, UI later.</strong> CLI workflows prove the runtime before dashboard work broadens the surface.</li>
<li><strong>Stigmem is the reference substrate.</strong> Local mode exists for onboarding and tests, but full durable behavior assumes Stigmem.</li>
</ol>

## Documentation model

Craik docs borrow the most useful patterns from three product lineages.

<div className="craik-grid">

<div>
<h4>From Stigmem</h4>
<p>Explicit concept docs · protocol &amp; contract reference · generated API/CLI reference once implementation exists · roadmap &amp; limitations · security &amp; governance · durable examples tied to real workflows · clear public/internal boundaries.</p>
</div>

<div>
<h4>From local agent runtimes</h4>
<p>Practical setup · workspace/project mental model · tool/skill/plugin docs · channel/adapter docs · operator-friendly examples.</p>
</div>

<div>
<h4>From multi-agent orchestration tools</h4>
<p>CLI-first user guides · configuration docs · skills docs · security/approval docs · multi-agent workflow docs · exact dependency &amp; supply-chain notes where relevant.</p>
</div>

</div>

Target docs tree:

```text
docs/
  concepts/
    durable-agent-runtime.md
    project-models.md
    case-files.md
    handoffs.md
    receipts.md
    work-graph.md
    memory-and-stigmem.md
    governance.md
    instruction-distillation.md
    skills-and-plugins.md
  guides/
    installation.md
    quickstart.md
    first-stigmem-reconciliation-demo.md
    configuring-craik-home.md
    connecting-stigmem.md
    using-case-files.md
    writing-handoffs.md
    running-policy-tests.md
    runner-adapters.md
    community-skills.md
    community-plugins.md
  reference/
    cli.md
    config.md
    schemas.md
    policy-profiles.md
    memory-backends.md
    runner-adapter-contract.md
    plugin-contract.md
  security/
    index.md
    redaction.md
    secrets.md
    capability-grants.md
    fail-open-profiles.md
  roadmap.md
  limitations.md
```

Root-level project governance files remain authoritative for
contribution, security disclosure, trademarks, and maintainership.

## MVP release strategy

<div className="craik-keypoint">

**`0.x.0` MVP first, `1.0.0` later.**

`1.0.0` is a later stability signal after real-world usage,
compatibility confidence, and security soak. The MVP still pulls
forward readiness work that affects trust: migrations, release
hygiene, package publication, generated docs, security process,
provider certification, public/internal boundaries, provenance
tracking, memory hygiene, and CI/CD depth.

The checkable MVP plan lives in
[Robust MVP Roadmap](mvp-roadmap.md). The release gates below
describe the contract and feature build-up through v0.12; the MVP
roadmap turns those surfaces into release-quality workflows.

</div>

## Release gates

Craik stays on `0.x.0` releases until the maintainers are confident
the product is stable enough to call `1.0`. The gates below are
sequencing targets, not promises that `1.0.0` follows immediately
after `0.7.0`. Additional `0.x.0` releases get added whenever the
product needs more soak time, compatibility work, security hardening,
or real-user validation.

### v0.1.0 · Governed agent-runtime substrate

<div className="craik-lead">

**Required outcome.** A user can register a real repo, authenticate
via OIDC, assemble a governed case file, compile runner prompts,
execute provider requests against OpenAI Responses / Anthropic
Messages / OpenAI-compatible Chat Completions adapters (fixture-backed
by default, live opt-in), resolve provider credentials through typed
profiles or workload-federated brokering, record receipts that name
both the operator identity and the credential identity, produce
durable handoffs, propose memory updates, and export the work graph.
Policy can constrain which operators and which credentials a task may
use; credential authorization is itself a receipted graph.

</div>

**Required capabilities:**

<div className="craik-grid">

<div><h4>Python 3.12+ package</h4><p>And <code>craik</code> CLI.</p></div>
<div><h4>MIT license</h4><p>And governance files.</p></div>
<div><h4>Local home</h4><p><code>~/.craik</code> default · <code>CRAIK_HOME</code> override.</p></div>
<div><h4>Pydantic contracts</h4></div>
<div><h4>SQLite local state</h4></div>
<div><h4>Project registry</h4></div>
<div><h4>Policy profiles</h4><p>Strict · trusted-local · automation.</p></div>
<div><h4>Capability grants</h4></div>
<div><h4>Central redaction utility</h4></div>
<div><h4>Receipt store</h4></div>
<div><h4>Handoff writer</h4></div>
<div><h4>Memory backends</h4><p>Local backend + Stigmem read client.</p></div>
<div><h4>Case-file assembler</h4><p>Evidence · assumptions · context budget · default exclusions with project/user overrides.</p></div>
<div><h4>Intent locks</h4><p>And self-audit before handoff.</p></div>
<div><h4>Memory proposals</h4><p>With diff and impact preview.</p></div>
<div><h4>Work graph export</h4></div>
<div><h4>Read-only GitHub adapter</h4></div>
<div><h4>Stigmem demo</h4><p>Docs reconciliation demo + behavior-test acceptance.</p></div>
<div><h4>Provider transport</h4><p><code>FixtureTransport</code> · <code>HTTPTransport</code> over stdlib urllib with SSE.</p></div>
<div><h4>Provider families</h4><p>OpenAI Responses · Anthropic Messages · OpenAI-compatible Chat Completions.</p></div>
<div><h4>Provider features</h4><p>Tool-call round-trip · streaming chunk capture · retry · timeout · cancellation.</p></div>
<div><h4>Single-agent loop</h4><p>Task run state machine · plan/act/observe/evaluate phases · runner step contract · per-step receipts and policy gates · output capture · memory proposal creation · handoff on completion/block/failure.</p></div>
<div><h4>Typed credentials</h4><p><code>auth-profiles.json</code> with <code>&lt;provider_family&gt;:&lt;name&gt;</code> IDs.</p></div>
<div><h4>Credential sources</h4><p>Env-var API key · local-CLI OAuth fallback · vendor-CLI subprocess bridge · external secret manager reference · marker · Stigmem-backed reference.</p></div>
<div><h4>Credential pool</h4><p>Rotation · failover · per-profile health.</p></div>
<div><h4>OIDC operator login</h4><p>Device-code · loopback+PKCE · IdP discovery · JWKS-validated ID tokens · refresh.</p></div>
<div><h4>Workload identity</h4><p>CI · Kubernetes · generic file · env-var.</p></div>
<div><h4>RFC 8693 token exchange</h4><p>Federated credential brokering.</p></div>
<div><h4>Operator session</h4><p><code>operator-session.json</code> · <code>craik login</code> · <code>craik logout</code> · <code>craik whoami</code>.</p></div>
<div><h4>Credential CLI</h4><p><code>craik auth list / add / remove / test / status / approve / grant</code>.</p></div>
<div><h4>Doctor integration</h4><p>Credential health surfaced in <code>craik doctor</code>.</p></div>
<div><h4>Identity on every call</h4><p>Operator and credential identity bound to every provider call and receipt.</p></div>
<div><h4>Policy-bound identity</h4><p><code>required_operator</code> · <code>allowed_operator_groups</code> · <code>allowed_credential_kinds</code> · <code>allowed_credential_profiles</code>.</p></div>
<div><h4>Approval-gated first use</h4><p>For any credential profile.</p></div>
<div><h4>Authorization binding</h4><p>Operator-credential receipted grant chain.</p></div>
<div><h4>Expiry as evidence</h4><p>Credential expiry surfaced as evidence/risk in case files.</p></div>
<div><h4>Per-credential redaction</h4></div>
<div><h4>Per-agent isolation</h4><p>Credential and operator isolation in handoff records (consumed by v0.3.0 multi-agent runtime).</p></div>

</div>

**Explicitly not required for v0.1.0:**

<div className="craik-grid">

<div><h4>Resumable runs</h4><p>Across process crashes.</p></div>
<div><h4>Real sandbox tool execution</h4></div>
<div><h4>Provider budget enforcement</h4><p>At the call boundary.</p></div>
<div><h4>Schema migration framework</h4></div>
<div><h4>Multi-agent runtime</h4><p>Beyond handoff identity bookkeeping.</p></div>
<div><h4>Instruction distillation pipeline</h4></div>
<div><h4>Operator UI / TUI</h4></div>
<div><h4>Gateway daemon</h4><p>And channel adapters.</p></div>
<div><h4>MCP client/server</h4></div>
<div><h4>Skill / plugin runtime</h4></div>
<div><h4>Learning loops</h4></div>
<div><h4>Companion surfaces</h4></div>
<div><h4>Migration tooling</h4></div>

</div>

### v0.2.0 · Durable execution continuity

<div className="craik-lead">

**Required outcome.** A run interrupted at any phase boundary can be
resumed cleanly with no duplicated side effects. Tool calls execute
inside at least one real sandbox backend, gated per call. Budgets are
enforced at the call boundary, not just declared. Persistent state
survives schema changes via a documented migration path.

</div>

The execution continuity slices have landed:
[#552](https://github.com/eidetic-labs/craik/issues/552) covers
phase-boundary resume and deterministic step idempotency keys.
[#554](https://github.com/eidetic-labs/craik/issues/554) covers
per-run wall-clock budget enforcement before new phase or tool rounds.
[#556](https://github.com/eidetic-labs/craik/issues/556) covers
provider token budget ledger updates and interruption before additional
provider calls once the budget is exhausted.
[#559](https://github.com/eidetic-labs/craik/issues/559) covers
operator-facing run inspection, resume, and cancellation commands.
[#561](https://github.com/eidetic-labs/craik/issues/561) covers
runtime exit-discipline checks persisted at the handoff boundary.
[#563](https://github.com/eidetic-labs/craik/issues/563) covers
tool-result attestations for dispatched provider tool calls.
[#565](https://github.com/eidetic-labs/craik/issues/565) covers
registered local-process sandbox execution for shell tool calls.
[#567](https://github.com/eidetic-labs/craik/issues/567) covers
cancellation propagation into in-flight local-process sandbox commands.
[#569](https://github.com/eidetic-labs/craik/issues/569) covers the
registered local-store migration runner and example migration.
[#571](https://github.com/eidetic-labs/craik/issues/571) covers the
CLI run-delta view for persisted continuity state.

<div className="craik-grid">

<div><h4>Resumable interrupted runs</h4><p>Shipped: interrupted runs reopen from persisted phase outputs and continue at the next unfinished phase.</p></div>
<div><h4>Step-level idempotency keys</h4><p>Shipped: stable keys are recorded in run state and runner step context to avoid duplicated phase outputs and side effects on replay.</p></div>
<div><h4>Time controls</h4><p>Shipped: per-run wall-clock budgets interrupt before the next phase or tool round when exhausted.</p></div>
<div><h4>Provider budget enforcement</h4><p>Shipped: provider token budgets are decremented from usage metadata and interrupt before the next provider call when exhausted.</p></div>
<div><h4>Run inspection &amp; recovery</h4><p>Shipped: <code>craik run show</code>, <code>craik run resume</code>, and <code>craik run cancel</code> expose persisted continuity state.</p></div>
<div><h4>Agent exit discipline</h4><p>Shipped: handoff creation persists exit-discipline checks so missing validation, risks, or next steps are runtime state.</p></div>
<div><h4>Tool result attestation</h4><p>Shipped: dispatched tool calls persist hashed attestations linked to the side-effect receipt and replay message.</p></div>
<div><h4>One real sandbox backend</h4><p>Shipped: <code>local_process</code> executes registered command references through <code>subprocess.run</code> without shell expansion when the loop is configured with a sandbox backend.</p></div>
<div><h4>Sandbox cancellation</h4><p>Shipped: local-process sandbox commands poll a cancellation event, terminate in-flight processes, and replay a cancelled tool result.</p></div>
<div><h4>Schema migration framework</h4><p>Shipped: local-store migrations run through a registered, forward-only migration runner with an example metadata migration.</p></div>
<div><h4>Run delta view</h4><p>Shipped: <code>craik run delta</code> renders persisted run-delta records and linked recovery sessions as an operator view or JSON.</p></div>

</div>

### v0.3.0 · Multi-agent review and coordination

<div className="craik-lead">

**Required outcome.** A handoff produced by agent A can be consumed by
agent B as the starting state of a new governed run. Two agents
working against the same project are coordinated via the work graph
and intent locks without colliding. Disagreement between agents
produces structured debate artifacts with receipted resolution.

</div>

<div className="craik-grid">

<div><h4>Handoff consumption</h4><p>Shipped first slice: <code>craik task resume --from-handoff=&lt;id&gt;</code> creates a new task, case file, and pending run with source handoff provenance and explicit consumer identity.</p></div>
<div><h4>Role-based dispatch</h4><p>Shipped first slice: provider-backed runs can dispatch implementer · verifier · adversarial reviewer · policy reviewer · docs reviewer · memory curator · adjudicator roles with policy allow-lists, dispatch receipts, and run metadata.</p></div>
<div><h4>Multi-agent message contract</h4><p>Shipped first slice: <code>craik agent-message send</code> and <code>craik agent-message receive</code> persist authenticated send/receive receipts and link to task, run, handoff, and role identities.</p></div>
<div><h4>Concurrent run coordination</h4><p>Shipped first slice: simultaneous loops on the same project are checked against active intent-lock scopes before new phases or tool dispatch, and overlapping scopes produce denial receipts.</p></div>
<div><h4>Structured debate runtime</h4><p>Shipped first slice: role-linked positions become typed debate turns, summaries preserve agreement or disagreement, and resolution records an adjudication or human-delegation receipt.</p></div>
<div><h4>Cross-agent review protocol</h4><p>Shipped first slice: review requests target worker results, handoffs, or debate summaries; review results carry typed findings, receipts, and source artifact links without mutating the reviewed artifact.</p></div>
<div><h4>Human delegation at runtime</h4><p>Shipped first slice: <code>craik delegation pause</code> interrupts a run with a receipted delegation request, <code>craik delegation resolve</code> records accepted/rejected/cancelled responses, and existing run resume continues from the interrupted boundary.</p></div>
<div><h4>Scope-change protocol</h4><p>Shipped first slice: discovered scope outside the active intent lock interrupts the run, persists a receipted request, and <code>craik scope-change decide</code> requires an explicit expand / sibling / handoff / denial decision.</p></div>
<div><h4>Live work graph</h4><p>Shipped first slice: v0.3.0 coordination artifacts persist work-graph events, and operators can query the active graph before final export.</p></div>
<div><h4>Per-agent isolation enforced</h4><p>Shipped first slice: handoff consumers record their own credential/operator assignment, producer identity reuse is denied by default, and intentional continuation requires an explicit flag plus rationale.</p></div>

</div>

### v0.4.0 · Runtime instruction distillation

<div className="craik-lead">

**Required outcome.** Declared instruction files in a repo are
ingested into typed, provenance-linked distillation items with
categorized extraction, stale invalidation, contradiction surfacing,
and an approval flow. Approved distillations participate in case
files and prompt compilation as first-class evidence.

</div>

<div className="craik-grid">

<div><h4>Source registry</h4><p>Shipped first slice: declared sources are registered explicitly with receipts, project confinement, symlink escape protection, and active source lists.</p></div>
<div><h4>Source ingestion</h4><p>Shipped first slice: <code>AGENTS.md</code> · <code>CLAUDE.md</code> · <code>GEMINI.md</code> · <code>HERMES.md</code> · <code>SKILLS.md</code> · <code>.cursorrules</code> · <code>.github/copilot-instructions.md</code> · <code>.codex/instructions.md</code> · declared policy docs parse through a project-confined pipeline.</p></div>
<div><h4>Source hash tracking</h4><p>Shipped first slice: newline-normalized SHA-256 snapshots track new, unchanged, changed, missing, and oversize source states with stale-invalidation input.</p></div>
<div><h4>Line/range provenance</h4><p>Shipped first slice: extracted statements retain source snapshot IDs, line/column ranges, summaries, and canonical excerpt hashes.</p></div>
<div><h4>Categorized extraction</h4><p>Shipped first slice: deterministic proposal creation covers instruction · policy · preference · command · boundary · handoff-rule · memory-rule · security-rule · stale-risk with unclassified warnings.</p></div>
<div><h4>Inter-source contradictions</h4><p>Shipped first slice: normalized cross-source conflicts create contradiction reports while same-source and stale candidates are skipped.</p></div>
<div><h4>Approval flow</h4><p>Shipped first slice: governing constraints require explicit operator approval, receipt HMAC verification, active-session identity binding, and override rationale for stale or contradicted proposals.</p></div>
<div><h4>Case-file integration</h4><p>Shipped first slice: governing distillations load as first-class evidence with provenance ranges and approval receipt snapshots.</p></div>
<div><h4>Prompt compilation</h4><p>Shipped first slice: governing distillations render in one sanitized, deterministic <code>Active instruction constraints</code> section with stale-exclusion warnings.</p></div>
<div><h4>Distillation CLI</h4><p>Shipped first slice: <code>craik instructions register / ingest / list / approve / reject / show</code> drives the lifecycle through the active operator session.</p></div>

</div>

### v0.5.0 · Quality, continuity, and recovery

<div className="craik-lead">

**Required outcome.** Craik helps agents recover, improve handoffs,
avoid stale context, and explain what changed between runs.

</div>

<div className="craik-grid">

<div><h4>Recovery mode</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/636">#636</a>. Recovery sessions and run deltas are persisted, HMAC-protected in the local store, and exposed through operator-gated <code>craik run recover</code> / <code>craik run delta</code>.</p></div>
<div><h4>Runtime critic</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/637">#637</a>. Reviewable, non-authoritative critic findings are captured through production helpers and <code>craik review critic</code>.</p></div>
<div><h4>Red team mode</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/638">#638</a>. Red-team findings are durable quality evidence captured through <code>craik review red-team</code> without becoming privileged instructions.</p></div>
<div><h4>Handoff quality score</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/640">#640</a>. Handoff creation persists deterministic score bands and names blocking reasons for poor handoffs.</p></div>
<div><h4>Evidence coverage score</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/639">#639</a>. Handoff creation persists missing evidence ids and weak claims as inspectable gaps.</p></div>
<div><h4>Context debt tracking</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/641">#641</a>. Omitted, stale, missing, and unresolved context becomes queryable debt with remediation state.</p></div>
<div><h4>Tool result attestation</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/643">#643</a>. Observed tool outputs are attested with trust class, evidence or receipt links, expiry, output-hash verification, and local HMAC integrity metadata.</p></div>
<div><h4>Knowledge freshness probes</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/644">#644</a>. Fresh, expiring, expired, and missing probes are captured through production helpers and produce stale-risk warnings.</p></div>
<div><h4>Evidence expiration rules</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/642">#642</a>. Expired and missing attestations are classified before reuse.</p></div>
<div><h4>Known traps</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/646">#646</a>. Active traps carry evidence, avoidance guidance, and expiry or contradiction state, and can be captured with <code>craik knowledge trap</code>.</p></div>
<div><h4>Negative knowledge</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/647">#647</a>. Evidence-backed negative statements remain scoped and freshness-bounded, and contradictions are opened instead of silently replacing positive assertions.</p></div>
<div><h4>Scratchpad with expiry</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/645">#645</a>. Temporary working notes are captured, expire, and are excluded from active summaries after expiry.</p></div>
<div><h4>First-class unknowns</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/648">#648</a>. Unresolved and resolved unknowns carry owner, next action, resolution state, and receipt linkage for resolution.</p></div>
<div><h4>Structured context requests</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/650">#650</a>. Missing context can be requested, fulfilled, cancelled, linked to handoffs, recovery, or unknowns, and fulfilled with receipt linkage.</p></div>
<div><h4>"What changed since last time" deltas</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/652">#652</a>. Run deltas summarize current and previous handoff, case-file, receipt, contradiction, and constraint state.</p></div>
<div><h4>Agent exit discipline</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/651">#651</a>. Handoff creation enforces validation, handoff, residual-risk, next-step, unknown, and open-context checks unless an explicit blocked-exit override rationale is recorded.</p></div>
<div><h4>Release readiness and docs assessment</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/649">#649</a>. Release-readiness docs now record v0.5.0 validation, remediation, and release-prep gates.</p></div>

</div>

### v0.6.0 · Skills, plugins, and ecosystem foundations

<div className="craik-lead">

**Required outcome.** Craik can support reusable skills and governed
plugins without weakening the runtime security model.

</div>

<div className="craik-grid">

<div><h4>Skill package format</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/659">#659</a>. Skill packages use semantic package versions, docs and entrypoints, no runtime authority, and explicit context declarations for expected inputs.</p></div>
<div><h4>Project-scoped &amp; global skills</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/660">#660</a>. Registries enforce project/global scope, active entry completeness, active-only precedence, and project override precedence.</p></div>
<div><h4>Context contracts for skills</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/661">#661</a>. Invocation contexts capture redacted inputs, outputs, omissions, policy links, receipts, and package requirement validation.</p></div>
<div><h4>Plugin descriptor format</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/662">#662</a>. Descriptors declare identity, trust boundary, semantic versioning, entrypoints, capability requests, docs, security notes, and compatibility without granting authority.</p></div>
<div><h4>Probationary plugins</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/663">#663</a>. Probation records keep new or changed plugins out of durable trust until criteria, evidence, compatibility checks, and decisions are recorded.</p></div>
<div><h4>Plugin capability grants</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/664">#664</a>. Plugin grants are descriptor-bound, evidence-linked, scoped to explicit operations and targets, approval-aware, and expiry-checked.</p></div>
<div><h4>Plugin receipts</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/665">#665</a>. Plugin receipts are redacted, descriptor-linked, grant-linked, evidence-linked, handoff-linked, and operator-visible with optional probation state.</p></div>
<div><h4>Adapter packages</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/666">#666</a>. Adapter packages declare semantic versions, entrypoints, capability surfaces, runner modes, Python/platform compatibility, docs, provenance, and linked plugins.</p></div>
<div><h4>Reference integrations</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/667">#667</a>. Reference integrations provide safe reproducible skill, plugin, and adapter examples with narrow matching links, checks, fixtures, receipts, and provenance.</p></div>
<div><h4>Community skills docs</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/668">#668</a>. The guide covers package authoring, context declarations, project/global registry scope, review expectations, and security boundaries.</p></div>
<div><h4>Community plugins docs</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/669">#669</a>. The guide covers descriptors, probation, grants, receipts, adapters, references, and no-ambient-authority review boundaries.</p></div>
<div><h4>Release readiness and docs assessment</h4><p>Ready: <a href="https://github.com/eidetic-labs/craik/issues/670">#670</a>. Release-readiness docs record v0.6.0 goal status, validation, security notes, blockers, changelog coverage, and release automation hygiene.</p></div>

</div>

### v0.7.0 · Operator experience

<div className="craik-lead">

**Required outcome.** Operators can inspect project state without
reading raw logs.

</div>

<div className="craik-grid">

<div><h4>Dashboard / TUI decision</h4><p>Ready in PR · CLI-first <code>craik operator overview</code> selected for v0.7.0.</p></div>
<div><h4>Work graph explorer</h4><p>Ready in PR · <code>craik operator work-graph</code> renders terminal and JSON graph inspection.</p></div>
<div><h4>Handoff viewer</h4><p>Ready in PR · <code>craik operator handoff</code> renders durable handoff summaries.</p></div>
<div><h4>Receipt viewer</h4><p>Ready in PR · <code>craik operator receipt</code> renders capability and plugin receipts.</p></div>
<div><h4>Contradiction inbox</h4><p>Ready in PR · <code>craik operator contradictions</code> lists review-only contradiction state.</p></div>
<div><h4>Evidence &amp; assumption views</h4><p>Ready in PR · <code>craik operator evidence</code> keeps assumptions separate from evidence.</p></div>
<div><h4>Delegation queue</h4></div>
<div><h4>Budget / quota view</h4></div>
<div><h4>Instruction distillation view</h4></div>
<div><h4>Quality gate view</h4></div>
<div><h4>Memory impact preview</h4></div>
<div><h4>Known traps view</h4></div>
<div><h4>Run delta view</h4></div>

</div>

### v0.8.0 · Operator integrations and always-on gateway

<div className="craik-lead">

**Required outcome.** Craik can run as an always-on operator service
with controlled ingress from external channels.

</div>

<div className="craik-grid">

<div><h4>Gateway daemon mode</h4></div>
<div><h4><code>craik setup</code> wizard</h4></div>
<div><h4><code>craik doctor</code> diagnostics</h4></div>
<div><h4><code>craik update</code> guidance</h4></div>
<div><h4>Channel adapter contract</h4></div>
<div><h4>First messaging channel adapter</h4></div>
<div><h4>Inbound identity &amp; pairing</h4></div>
<div><h4>Channel allowlists</h4></div>
<div><h4>Channel-scoped policy envelopes</h4></div>
<div><h4>Webhook ingress</h4></div>
<div><h4>Scheduled automations</h4></div>
<div><h4>Cron-like task creation</h4></div>
<div><h4>Gateway receipts</h4></div>
<div><h4>Gateway troubleshooting docs</h4></div>

</div>

<div className="craik-keypoint">

**Deferred until this phase or later.**

Broad channel matrix · consumer assistant positioning · open inbound
DM behavior · mobile companion surfaces.

</div>

### v0.9.0 · Execution environments, sandboxes, and provider routing

<div className="craik-lead">

**Required outcome.** Craik can choose model/provider/runtime
execution paths and enforce environment boundaries explicitly across
multiple sandbox backends.

</div>

<div className="craik-grid">

<div><h4>Model provider registry</h4></div>
<div><h4>Provider switching UX</h4></div>
<div><h4>Provider failover policy</h4></div>
<div><h4>Provider budget &amp; quota links</h4></div>
<div><h4>MCP client integration</h4></div>
<div><h4>MCP server / export decision</h4></div>
<div><h4>Local process backend</h4></div>
<div><h4>Docker sandbox backend</h4></div>
<div><h4>SSH or remote shell backend</h4></div>
<div><h4>Browser / tool execution boundary</h4></div>
<div><h4>Environment capability receipts</h4></div>
<div><h4>Sandbox policy tests</h4></div>
<div><h4>Provider routing docs</h4></div>

</div>

### v0.10.0 · Self-improving skills and learning loops

<div className="craik-lead">

**Required outcome.** Craik can improve reusable operating guidance
without allowing agents to silently rewrite their own authority.

</div>

<div className="craik-grid">

<div><h4>Skill performance telemetry</h4></div>
<div><h4>Autonomous skill proposals</h4></div>
<div><h4>Skill improvement proposals</h4></div>
<div><h4>Skill eval / replay harness</h4></div>
<div><h4>Periodic memory review nudges</h4></div>
<div><h4>Preference modeling as facts</h4></div>
<div><h4>Learning-loop receipts</h4></div>
<div><h4>Promotion approval gates</h4></div>
<div><h4>Rollback path</h4><p>For bad skill updates.</p></div>
<div><h4>Trajectory export format</h4></div>
<div><h4>Trajectory compression</h4></div>
<div><h4>Learning-loop docs</h4></div>

</div>

Builds on instruction distillation and the skill/plugin system. Agents
may propose changes to skills, but changes remain reviewable until
policy allows promotion.

### v0.11.0 · Multimodal and companion surfaces

<div className="craik-lead">

**Required outcome.** Craik can expose durable agent work through
richer operator surfaces without compromising its policy and evidence
model.

</div>

<div className="craik-grid">

<div><h4>Voice I/O posture</h4></div>
<div><h4>Speech-to-text adapter contract</h4></div>
<div><h4>Text-to-speech adapter contract</h4></div>
<div><h4>Multimodal artifact references</h4></div>
<div><h4>Desktop companion app decision</h4></div>
<div><h4>Mobile companion app decision</h4></div>
<div><h4>Visual workspace decision</h4></div>
<div><h4>Work graph → workspace bridge</h4></div>
<div><h4>Accessibility requirements</h4></div>
<div><h4>Companion app security docs</h4></div>
<div><h4>Multimodal redaction tests</h4></div>

</div>

<div className="craik-keypoint">

**Optional phase.**

This phase is optional unless Craik deliberately competes with
personal-assistant surfaces. It must not block server-side
software-delivery workflows.

</div>

### v0.12.0 · Migration, i18n, and ecosystem compatibility

<div className="craik-lead">

**Required outcome.** Teams can adopt Craik from adjacent tools and
operate it in broader language and ecosystem contexts.

</div>

<div className="craik-grid">

<div><h4>Adjacent-tool migration assessment</h4></div>
<div><h4>Multi-agent tool migration assessment</h4></div>
<div><h4>Import dry-run reports</h4></div>
<div><h4>Memory / skill / config migration maps</h4></div>
<div><h4>Secret migration policy</h4></div>
<div><h4>MCP ecosystem compatibility guide</h4></div>
<div><h4>Adjacent-runtime bridge decision</h4></div>
<div><h4>Multi-agent workflow bridge decision</h4></div>
<div><h4>Locale / i18n framework</h4></div>
<div><h4>Translated docs strategy</h4></div>
<div><h4>Ecosystem compatibility tests</h4></div>

</div>

### Post-MVP stability · Professional agent runtime

<div className="craik-lead">

**Required outcome.** Craik is stable enough for external teams to use
for real multi-agent software-delivery workflows.

</div>

<div className="craik-keypoint">

**Graduation gate, not a scheduled release.**

Ship a robust `0.x.0` MVP first, then continue shipping `0.x.0`
releases until the bar below is met by real usage, documentation
maturity, compatibility confidence, and security posture.

</div>

**Required capabilities.** MVP-readiness items are tracked in
[Robust MVP Roadmap](mvp-roadmap.md) before the first usable `0.x.0`.

<div className="craik-grid">

<div><h4>Stable core schemas</h4></div>
<div><h4>Migration path</h4><p>For persisted state.</p></div>
<div><h4>SemVer release process</h4></div>
<div><h4>Package publication</h4></div>
<div><h4>Security release process</h4></div>
<div><h4>Complete CLI/reference docs</h4></div>
<div><h4>Production Stigmem integration</h4></div>
<div><h4>Documented limits &amp; failure modes</h4></div>
<div><h4>Runnable demo</h4></div>
<div><h4>Community contribution path</h4></div>
<div><h4>≥1 complete runner adapter end-to-end</h4></div>
<div><h4>Policy tests in CI</h4></div>
<div><h4>Public/internal boundary classifier</h4></div>
<div><h4>Provenance-aware documentation</h4></div>
<div><h4>Memory hygiene workflow</h4></div>
<div><h4>Work product classification</h4></div>
<div><h4>Decision record suggestions</h4></div>
<div><h4>Learning without self-trust</h4></div>

</div>

**Confidence requirements before `1.0.0`:**

<ol className="craik-steps">
<li>At least one complete runner adapter has been used successfully on real workflows.</li>
<li>Stigmem-backed memory has soaked on real projects.</li>
<li>Persisted schema migrations have been exercised.</li>
<li>Security and redaction behavior has been tested under realistic agent runs.</li>
<li>Documentation is complete enough for external users without maintainer hand-holding.</li>
<li>Community contribution and support expectations are clear.</li>
<li>Known limitations are documented honestly.</li>
</ol>

## Executable workstreams

Each workstream below becomes one or more GitHub milestones/issues.
Documentation requirements are part of the definition of done.

### 0 · Project foundation

**Scope:** package metadata · Python 3.12+ skeleton · `craik` CLI · MIT license · governance files · dependency lock strategy · CI quality gates · package-name reservation or publication.

**Validation:** `craik --version` works · tests run in CI · lint/type checks run in CI · package metadata validates.

**Docs:** installation · quickstart stub · contribution guide updates · release/support note · limitations note for pre-`0.1.0`.

### 1 · Runtime contracts

**Scope:** task request · project profile · policy envelope · capability grant · capability receipt · case file · agent role · worker result · handoff · memory proposal · memory backend capabilities · contradiction report · work graph event · evidence reference · assumption · delegation point · intent lock · instruction distillation item · quality gate result · artifact classification.

**Validation:** schema fixtures · invalid fixture tests · JSON serialization tests · version field tests.

**Docs:** schema reference · examples for each contract · versioning and migration policy.

### 2 · Local state and project registry

**Scope:** `~/.craik` default home · `CRAIK_HOME` override · `config/` · `secrets/` · `state/` · `cache/` · `logs/` · `receipts/` · `handoffs/` · `case-files/` · `projects/` · secure permissions where supported · SQLite store · project registry · immutable path config · project-local `.craik/` opt-in only.

**Validation:** path resolver tests · permission tests · registry persistence tests · project-local opt-in tests.

**Docs:** configuring Craik home · local state layout reference · secrets handling guide.

### 3 · Policy, grants, redaction, receipts

**Scope:** strict / trusted-local / automation profiles · fail-open profile visibility · capability grants · immutable path protection · central redaction utility · shell/file/GitHub/memory grant enforcement · receipt persistence · policy denial receipts.

**Validation:** policy fixture tests · redaction tests · immutable-path tests · fail-open receipt tests · automation fail-closed tests.

**Docs:** policy profiles reference · fail-open guide · capability grants guide · redaction and secrets docs.

### 4 · Case files, intent, evidence, assumptions

**Scope:** task intent lock · repository state ingestion · docs and ADR discovery · default discovery exclusions for generated/dependency/build/cache/archive-heavy paths · project and user override rules · visible context-debt metadata · Stigmem/local fact loading · GitHub context placeholders · evidence references · assumption ledger · context budget metadata · stale-risk markers · context explanations · structured context requests · first-class unknowns · context debt tracking.

**Validation:** deterministic fixture output · evidence reference tests · assumption promotion tests · context inclusion/exclusion tests · default exclusion tests · override tests · stale-risk tests.

**Docs:** case file concept doc · using case files guide · evidence and assumptions guide · context budgeting guide · context discovery and exclusion guide.

### 5 · Handoffs, self-audit, exit discipline

**Scope:** structured handoff · Markdown handoff · self-audit before handoff · incomplete-run handoff · handoff quality score · unresolved questions · next steps · receipt links · memory proposal links · context debt links.

**Validation:** handoff schema tests · self-audit checklist tests · quality score fixture tests · interrupted-run fixture tests.

**Docs:** handoff concept doc · writing handoffs guide · self-audit reference · recovery and incomplete-run guide.

### 6 · Memory backends and Stigmem integration

**Scope:** ephemeral backend · local backend · Stigmem backend · capability detection · health and metadata checks · fact query/list/get/write · provenance reads · optional recall · optional conflicts · local proposal model · memory diff · memory impact preview · source identity handling · source attestation handling · error mapping.

**Validation:** backend interface tests · local backend persistence tests · Stigmem integration tests against a local node · auth failure tests · optional-capability fallback tests · memory diff tests.

**Docs:** memory backend reference · connecting Stigmem guide · Stigmem compatibility matrix · memory proposal and promotion guide · memory impact preview guide.

### 7 · GitHub adapter and demo workflow

**Scope:** GitHub auth detection · repository metadata · issues · PRs · changed files · check status · guarded GitHub comments/issues/PR creation · first Stigmem docs reconciliation demo.

**Validation:** mocked GitHub adapter tests · read-only fallback tests · permission failure tests · fixture demo run.

**Docs:** GitHub adapter guide · first Stigmem reconciliation demo · public/internal boundary guidance · troubleshooting guide.

### 8 · Work graph, contradictions, delegation

**Scope:** graph nodes and edges · task/handoff/fact/proposal/receipt/evidence/assumption/delegation/artifact nodes · contradiction reports · Stigmem conflict linking · local contradiction reports · human delegation points · approval/clarification/policy-override/memory-promotion/release-signoff requests.

**Validation:** graph export tests · contradiction lifecycle tests · delegation lifecycle tests · unresolved delegation block tests.

**Docs:** work graph concept doc · contradiction inbox guide · human delegation guide · graph export reference.

### 9 · Agent-native onboarding

**Scope:** `craik onboard --project <project-id>` · project model · active policies · ADRs and immutable paths · docs boundaries · recent handoffs · unresolved contradictions · stale-risk warnings · validation commands · Stigmem status · known traps · allowed next actions.

**Validation:** onboarding fixture tests · missing context tests · stale context tests · runner-readable output tests.

**Docs:** onboarding guide · known traps guide · project model concept doc.

### 10 · Runner adapters

**Scope:** runner adapter interface · Codex adapter · Claude adapter · Gemini adapter · runner capability matrix · policy-aware prompt compiler · runner metadata · normalized worker results · normalized handoffs · real-runner contract tests · runner trust profiles.

**Validation:** adapter interface tests · fixture contract tests · prompt compilation tests · runner capability matrix tests · real-runner smoke tests when credentials/tools are available.

**Docs:** runner adapter contract · Codex adapter guide · Claude adapter guide · Gemini adapter guide · prompt compiler reference · runner capability matrix reference.

### 11 · Single-agent execution loop

**Scope:** run id and run status model · task run state machine · plan/act/observe/evaluate/continue/stop phases · runner step contract · bounded case-file context with default exclusions and overrides · max-iteration limit · timeout and budget limits · intent-lock stop-condition enforcement · approval and grant checks before side effects · step receipts · observed output capture · memory proposal hooks · handoff on completion/block/failure/interruption · run resume · run recovery · agent exit discipline.

**Validation:** state-machine transition tests · max-iteration and timeout tests · budget exhaustion tests · stop-condition enforcement tests · approval-block tests · receipt-per-step tests · interrupted-run resume tests · handoff-on-failure tests · runner fixture tests · polluted-context fixture tests.

**Docs:** single-agent execution loop concept doc · running tasks guide · run state reference · resume and recovery guide · loop policy guide · context discovery override guide.

### 12 · Multi-agent coordination

**Scope:** orchestrator · specialist tasks · parallel read-only investigations · implementer/verifier/adversarial-reviewer/policy-reviewer/docs-reviewer/memory-curator/release-reviewer/adjudicator roles · typed worker results · cross-agent review protocol · structured agent debate · scope-change protocol.

**Validation:** child task graph tests · typed worker result tests · debate/adjudication fixture tests · unresolved-contradiction block tests · scope-change proposal tests.

**Docs:** multi-agent workflows guide · role reference · review protocol guide · structured debate guide.

### 13 · Runtime instruction distillation

**Scope:** declared instruction source registry · `AGENTS.md` · `CLAUDE.md` · `GEMINI.md` · `HERMES.md` · `SKILLS.md` · `.cursorrules` · `.github/copilot-instructions.md` · `.codex/instructions.md` · source hash tracking · line/range provenance · extraction categories · distillation proposals · stale distillation invalidation · instruction contradiction reports · promotion approval.

**Validation:** Markdown fixture tests · source hash invalidation tests · extraction category tests · contradiction fixture tests · approval/promotion tests.

**Docs:** instruction distillation concept doc · declaring instruction sources guide · distillation review guide · instruction categories reference.

### 14 · Quality gates and freshness

**Scope:** runtime critic · red team mode · evidence coverage score · tool result attestation · knowledge freshness probes · evidence expiration rules · negative knowledge · runtime memory hygiene · decision record suggestions · learning without self-trust.

**Validation:** critic fixture tests · red team policy tests · evidence coverage tests · tool-result source tests · freshness probe tests · memory hygiene proposal tests.

**Docs:** quality gates guide · freshness and staleness guide · negative knowledge guide · memory hygiene guide · decision record suggestion guide.

### 15 · Budgets, quotas, and operational bounds

**Scope:** context token budgets · model spend budgets · wall-clock budgets · shell command count · GitHub write count · memory write count · parallel worker count · retry count · approval count · budget receipts · budget escalation/block behavior.

**Validation:** budget accounting tests · exhaustion behavior tests · fail-open budget receipt tests · policy profile budget tests.

**Docs:** budget and quota guide · policy budget reference · troubleshooting budget exhaustion.

### 16 · Recovery and continuity

**Scope:** recovery mode · partial receipt loading · scratchpad restore · changed file detection · unfinished handoff recovery · unresolved delegation restore · "what changed since last time" deltas · run delta summaries.

**Validation:** interrupted-run fixtures · recovery command tests · delta calculation tests · partial handoff tests.

**Docs:** recovery guide · run deltas guide · interruption handling reference.

### 17 · Artifact and documentation intelligence

**Scope:** work product classification · provenance-aware documentation · public/internal boundary classifier · generated doc evidence links · docs stale-state detection · release note classification · audit artifact classification.

**Validation:** classifier fixture tests · public/internal boundary tests · provenance link tests · stale doc fixture tests.

**Docs:** artifact classification reference · provenance-aware docs guide · public/internal boundary guide · docs maintenance guide.

### 18 · Skills, plugins, and community ecosystem

**Scope:** skill package format · project-scoped skills · global skills · community skills layout · plugin descriptor format · probationary plugin policy · plugin capability grants · plugin receipts · adapter package guidance · reference integrations · marketplace/index format decision.

**Validation:** skill loader tests · plugin descriptor validation tests · probationary policy tests · plugin receipt tests · community package fixture tests.

**Docs:** skills concept doc · writing skills guide · community skills guide · plugin contract reference · writing plugins guide · plugin security guide · marketplace/index guide.

### 19 · Operator experience

**Scope:** TUI/dashboard decision · work graph explorer · handoff viewer · receipt viewer · contradiction inbox · evidence and assumption views · delegation queue · budget view · instruction distillation view · quality gate view · memory impact preview · known traps view · run delta view.

**Validation:** UI/TUI smoke tests · nonblank rendering checks · fixture state rendering tests · accessibility and keyboard navigation checks for UI surfaces.

**Docs:** operator guide · dashboard/TUI guide · view reference · troubleshooting guide.

### 20 · Operator integrations and always-on gateway

**Scope:** gateway daemon mode · setup wizard · diagnostics command · update guidance · channel adapter contract · first messaging channel adapter · inbound identity and pairing model · channel allowlists · channel-scoped policy envelopes · webhook ingress · scheduled automations · gateway receipts.

**Validation:** daemon lifecycle tests · setup wizard fixture tests · diagnostics failure-mode tests · webhook signature tests · channel identity mapping tests · scheduled task creation tests · gateway receipt tests.

**Docs:** gateway guide · setup guide · diagnostics guide · channel adapter reference · webhook reference · scheduler guide · gateway security guide.

### 21 · Execution environments, sandboxes, provider routing

**Scope:** model provider registry · provider switching UX · provider failover policy · provider budget and quota links · MCP client integration · MCP server/export decision · sandbox backend contract · local process backend · Docker sandbox backend · SSH or remote shell backend · browser/tool execution boundary · environment capability receipts.

**Validation:** provider registry tests · provider failover tests · MCP compatibility fixture tests · sandbox policy tests · backend isolation tests · environment receipt tests · budget linkage tests.

**Docs:** provider routing guide · provider config reference · MCP integration guide · sandbox backend reference · execution environment security guide.

### 22 · Self-improving skills and learning loops

**Scope:** skill performance telemetry · autonomous skill proposal creation · skill improvement proposals · skill eval/replay harness · periodic memory review nudges · user/team preference facts · learning-loop receipts · approval gates for promoted skills · rollback path for bad skill updates · training/trajectory export format · trajectory compression or summarization.

**Validation:** skill proposal tests · skill eval fixture tests · replay determinism tests · approval gate tests · rollback tests · trajectory export tests · learning-loop receipt tests.

**Docs:** skill improvement guide · learning-loop policy guide · skill eval reference · trajectory export reference · rollback guide.

### 23 · Multimodal and companion surfaces

**Scope:** voice input/output posture · speech-to-text adapter contract · text-to-speech adapter contract · multimodal artifact references · desktop companion app decision · mobile companion app decision · live visual workspace/canvas decision · work graph to visual workspace bridge · accessibility requirements.

**Validation:** multimodal artifact schema tests · redaction tests for transcript and media metadata · accessibility checks for companion surfaces · visual workspace smoke tests where implemented · adapter contract tests.

**Docs:** multimodal posture doc · voice adapter reference · companion app security guide · visual workspace guide · accessibility checklist.

### 24 · Migration, i18n, and ecosystem compatibility

**Scope:** adjacent-tool import/migration assessment · multi-agent workflow import/migration assessment · import dry-run reports · memory/skill/config migration maps · secret migration policy · ecosystem compatibility guide · adjacent runtime bridge decision · multi-agent workflow bridge decision · locale/i18n framework · translated docs strategy.

**Validation:** import dry-run fixture tests · migration map tests · secret redaction tests · bridge compatibility smoke tests where implemented · locale fallback tests · translated docs link tests where applicable.

**Docs:** migration guide · import dry-run reference · secret migration policy · ecosystem compatibility guide · i18n guide · bridge decision records.

## v0.1.0 issue cut

The initial issue set covers only the `v0.1.0` gate and any contracts
needed to avoid rework.

<ol className="craik-steps">
<li>Scaffold Python package and <code>craik</code> CLI.</li>
<li>Add core Pydantic schemas and fixtures.</li>
<li>Implement <code>~/.craik</code> path resolver and local state layout.</li>
<li>Implement SQLite local store.</li>
<li>Implement project registry.</li>
<li>Implement strict / trusted-local / automation policy profiles.</li>
<li>Implement capability grants and immutable path protection.</li>
<li>Implement central redaction utility.</li>
<li>Implement receipt store.</li>
<li>Implement case file assembler with evidence, assumptions, and context budget metadata.</li>
<li>Implement intent lock.</li>
<li>Implement handoff writer and self-audit checklist.</li>
<li>Implement local memory backend and proposal flow.</li>
<li>Implement Stigmem backend minimum compatibility.</li>
<li>Implement memory diff and memory impact preview foundations.</li>
<li>Implement GitHub read adapter.</li>
<li>Implement work graph export.</li>
<li>Implement contradiction report model.</li>
<li>Implement agent-native onboarding.</li>
<li>Implement policy test harness and core policy tests.</li>
<li>Implement Stigmem documentation reconciliation demo.</li>
<li>Build initial docs tree and publish v0.1.0 user/concept/reference docs.</li>
</ol>

**Each issue includes:** implementation checklist · test/validation
checklist · documentation checklist · security/policy impact · Stigmem
fact update requirement when relevant.

## Goal issue workflow

For each `0.x.0` goal issue, implementation is not complete until the
change has a pull request and the pull request has passed required CI.
The working branch is pushed after implementation, tests, docs, and
local validation are complete. Then the PR checks are watched to a
terminal state. If any required check fails, fix the failure in the same
PR branch, push again, and repeat the check wait before closing the issue
or marking the goal complete.

Do not close milestone issues from local validation alone. The goal
workflow requires the PR branch to be current on GitHub and the required
PR gates to be green. If the agent opened the PR and the checks are
clean, the agent merges the PR, verifies the merge landed on the base
branch, prunes stale local and remote branches, and only then moves to
the next goal.

## Documentation definition of done

<div className="craik-grid">

<div><h4>What concept changed?</h4></div>
<div><h4>What user workflow changed?</h4></div>
<div><h4>What CLI / API / config changed?</h4></div>
<div><h4>What policy or security behavior changed?</h4></div>
<div><h4>What examples should exist?</h4></div>
<div><h4>What limitations apply?</h4></div>
<div><h4>What facts should future agents know?</h4></div>

</div>

For implementation issues, docs are updated in the same PR unless the
issue is explicitly internal-only scaffolding.

## Release definition of done

<div className="craik-grid">

<div><h4>Passing tests</h4></div>
<div><h4>Passing lint / type checks</h4></div>
<div><h4>Generated or updated CLI/reference docs</h4></div>
<div><h4>Updated roadmap state</h4></div>
<div><h4>Updated limitations</h4></div>
<div><h4>Security notes</h4></div>
<div><h4>Migration notes</h4><p>When local state or schemas change.</p></div>
<div><h4>Runnable demo status</h4></div>
<div><h4>Memory update</h4><p>Optional release-state memory only when Stigmem is available; this is not a release gate.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../mvp-roadmap/">
<strong>Read</strong>
<span>MVP roadmap</span>
<small>The checkable v0.x.0 plan that turns these gates into release-quality workflows.</small>
</a>

<a href="../limitations/">
<strong>Read</strong>
<span>Limitations</span>
<small>Honest scope boundary for what's end-to-end today.</small>
</a>

<a href="../implementation-plan/">
<strong>Read</strong>
<span>Implementation plan</span>
<small>The buildable sequence under the chosen stack.</small>
</a>

</div>
