# Schema reference

<p className="craik-meta"><span>5 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

Craik runtime contracts as strict Pydantic models, how to inspect
them, the full v0.1.0 contract catalog, the fixture path used by
tests, and the versioning/migration rules.

</div>

<div className="craik-keypoint">

**Every persisted contract is versioned.**

Every persisted record includes a `schema` and `version` field.
Unknown fields are rejected so adapters, memory backends, and future
plugins don't silently depend on accidental payload shape.

</div>

```json
{
  "schema": "craik.<contract-name>",
  "version": "0.1.0"
}
```

## Inspecting schemas

```sh
craik schema list
craik schema show craik.task_request
```

## v0.1.0 contracts

| Schema | Purpose |
| --- | --- |
| `craik.adjudication_outcome` | Records adjudicator decisions over reviewed specialist outputs and unresolved disagreements. |
| `craik.adapter_package` | Defines runner adapter package metadata, compatibility, entrypoints, capability surfaces, provenance, and version constraints. |
| `craik.agent_onboarding` | Summarizes runner-readable project context before an agent starts work. |
| `craik.agent_role` | Defines a policy-aware orchestrator or specialist role for multi-agent coordination. |
| `craik.agent_session_event` | Records redacted prompt-loop, run, handoff, receipt, interruption, and exit events for persistent agent sessions. |
| `craik.agent_session_state` | Records persistent agent lifecycle, provider, model, operator, policy, recovery, and redacted process metadata. |
| `craik.assumption` | Tracks unresolved assumptions that need evidence before promotion to fact. |
| `craik.capability_grant` | Defines scoped permission for an action family. |
| `craik.capability_receipt` | Records an auditable action result under a policy profile. |
| `craik.case_file` | Captures task-specific context assembled before execution. |
| `craik.channel_allowlist` | Defines deny-by-default channel ingress allowlist rules and audit requirements. |
| `craik.channel_adapter_contract` | Defines external channel adapter identity, payload shapes, capability surfaces, receipts, and trust boundaries. |
| `craik.channel_identity_pairing` | Records external channel account pairing state, policy linkage, revocation state, and audit links. |
| `craik.compiled_prompt` | Captures a deterministic policy-aware runner prompt. |
| `craik.contradiction_report` | Captures incompatible assertions for review. |
| `craik.context_debt_record` | Tracks omitted, stale, unresolved, or missing context with owner and next action. |
| `craik.context_request` | Requests missing context and links it to handoffs, recovery, or unknowns. |
| `craik.debate_summary` | Summarizes agreement, unresolved disagreement, or contradiction escalation for a bounded agent debate. |
| `craik.debate_turn` | Captures one role-linked debate contribution with evidence, assumptions, and contradiction links. |
| `craik.distilled_instruction_proposal` | Captures a reviewable instruction distilled from declared instruction sources. |
| `craik.evidence_coverage_score` | Scores whether expected evidence links are present for a handoff or output. |
| `craik.evidence_reference` | Points to source material supporting a contract assertion. |
| `craik.exit_discipline_check` | Verifies validation, handoff, risks, next steps, and context links before exit. |
| `craik.gateway_config` | Configures the always-on gateway process mode, bind, policy, and pid/log paths. |
| `craik.gateway_runtime_state` | Records supervised gateway lifecycle state, process id, receipts, and notes. |
| `craik.gateway_schedule` | Defines a cron-like gateway schedule that can create policy-linked tasks. |
| `craik.handoff` | Summarizes durable run state for future agents. |
| `craik.handoff_quality_score` | Scores handoff completeness, validation, evidence links, debt, and risks. |
| `craik.human_delegation_point` | Records an open or resolved human approval, clarification, escalation, or ownership-transfer point. |
| `craik.instruction_registry_receipt` | Records the auditable result of registering a declared instruction source. |
| `craik.instruction_provenance` | Links distilled instruction material to source-level or line/range provenance. |
| `craik.instruction_promotion_review` | Records approved, rejected, or deferred promotion decisions for distilled instructions. |
| `craik.instruction_source` | Declares one runtime instruction source file or policy doc. |
| `craik.instruction_source_registration` | Captures one source-registration event with owner, actor, trust boundary, and optional content hash. |
| `craik.instruction_source_registry` | Registers declared instruction sources for a project. |
| `craik.instruction_source_snapshot` | Records source hash state for one observed instruction source. |
| `craik.intent_lock` | Preserves task intent and scope boundaries. |
| `craik.knowledge_freshness_probe` | Tracks fresh, expiring, expired, or missing knowledge for stale-risk warnings. |
| `craik.known_trap` | Records evidence-backed pitfalls and avoidance guidance for agents. |
| `craik.memory_backend_capabilities` | Records detected memory backend support. |
| `craik.memory_diff` | Explains run-scoped memory reads, proposals, writes, and failures. |
| `craik.memory_impact_preview` | Previews memory additions, invalidations, evidence gaps, and likely contradictions. |
| `craik.memory_proposal` | Describes reviewable memory updates. |
| `craik.model_provider` | Defines model provider identity, modes, capabilities, trust boundary, config references, and secret reference names. |
| `craik.negative_knowledge` | Records evidence-backed negative statements with scope and freshness boundaries. |
| `craik.policy_envelope` | Defines runtime authority and obligations. |
| `craik.plugin_capability_grant` | Defines least-privilege plugin-scoped capability grants with policy, approval, expiry, evidence, and receipt links. |
| `craik.plugin_descriptor` | Defines governed plugin identity, entrypoints, capability declarations, docs, security metadata, and compatibility without granting authority. |
| `craik.plugin_probation` | Tracks probationary plugin criteria, compatibility checks, evidence, receipts, and promotion, rejection, or expiration decisions. |
| `craik.plugin_receipt` | Records redacted plugin actions and outputs with descriptor, grant, evidence, handoff, and trust-boundary links. |
| `craik.project_profile` | Defines a project Craik can reason about. |
| `craik.promoted_instruction_constraint` | Captures an approved distilled instruction as an active runtime constraint. |
| `craik.reference_integration` | Describes safe reproducible sample skill, plugin, or adapter paths with docs, fixtures, checks, receipts, compatibility, and provenance. |
| `craik.red_team_finding` | Captures reviewable adversarial findings and blockers for high-risk work. |
| `craik.recovery_session` | Summarizes resume readiness and required recovery actions for an agent. |
| `craik.review_request` | Requests bounded cross-agent review of worker results or debate summaries. |
| `craik.review_result` | Captures specialist reviewer decisions, evidence, and preserved reviewer role kind. |
| `craik.run_delta` | Records continuity-relevant changes since the previous usable handoff. |
| `craik.run_output` | Stores redacted observed output captured from one runner step. |
| `craik.runtime_critic_finding` | Captures reviewable non-authoritative quality findings from a critic pass. |
| `craik.scheduled_automation` | Records an enabled or disabled gateway automation backed by a persisted schedule and policy envelope. |
| `craik.scratchpad_record` | Stores expiring temporary working notes that must not become durable context by default. |
| `craik.scope_change_request` | Requests a human decision to change accepted task scope. |
| `craik.scope_change_result` | Records accepted or rejected human scope-change decisions. |
| `craik.skill_invocation_context` | Captures policy-linked, redacted inputs, outputs, omissions, evidence, and receipts for one skill run. |
| `craik.skill_package` | Defines reusable skill metadata, entrypoints, docs, assets, and schema expectations. |
| `craik.skill_registry` | Registers project-local and global skill entries with trust boundaries, precedence, and provenance. |
| `craik.runner_adapter_request` | Defines normalized input handed to a runner adapter. |
| `craik.runner_adapter_result` | Defines normalized output returned by a runner adapter. |
| `craik.runner_capability_matrix` | Defines runner capability support, trust boundary, and default grant posture. |
| `craik.runner_metadata` | Defines stable runner identity, mode, and capability summary. |
| `craik.runner_step_request` | Defines one governed loop-step input for a runner. |
| `craik.runner_step_result` | Captures one governed loop-step result, diagnostics, receipts, and proposals. |
| `craik.task_run` | Tracks durable single-agent run status, phase, linked artifacts, receipts, and handoff. |
| `craik.task_request` | Defines requested work. |
| `craik.tool_result_attestation` | Records observed tool or command output with trust and expiry boundaries. |
| `craik.unknown_record` | Tracks first-class unknowns, required resolution source, and resolved answers. |
| `craik.work_graph_export` | Exports connected graph nodes and edges. |
| `craik.work_graph_event` | Updates the work graph. |
| `craik.worker_result` | Captures typed specialist worker output for multi-agent coordination. |

## Examples

Fixture examples for every v0.1.0 contract live in:

```text
tests/fixtures/contracts/v0_1/contracts.json
```

Fixtures are loaded by tests, validated against the registered
Pydantic models, and round-tripped through JSON.

## Versioning and migration

<div className="craik-fields">

<div>
<dt>Rule</dt>
<dt><span className="craik-fields__type">Applies to</span></dt>
<dd>Required action</dd>
</div>

<div>
<dt>Compatible field additions</dt>
<dt><span className="craik-fields__type">minor</span></dt>
<dd>Require tests, docs, and fixture updates.</dd>
</div>

<div>
<dt>Breaking changes</dt>
<dt><span className="craik-fields__type">major</span></dt>
<dd>New schema version + migration notes.</dd>
</div>

<div>
<dt>Unknown fields</dt>
<dt><span className="craik-fields__type">runtime</span></dt>
<dd>Rejected by default.</dd>
</div>

<div>
<dt>Memory writes</dt>
<dt><span className="craik-fields__type">durable</span></dt>
<dd>Preserve source, confidence, scope, and trust metadata.</dd>
</div>

<div>
<dt>Policy / receipt contracts</dt>
<dt><span className="craik-fields__type">governance</span></dt>
<dd>Preserve profile, fail-open, redaction, and approval metadata.</dd>
</div>

<div>
<dt>Adapter receipts / handoffs</dt>
<dt><span className="craik-fields__type">runner output</span></dt>
<dd>Preserve stable runner metadata; keep provider-specific details nested and redacted.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../../runtime-contracts/">
<strong>Read</strong>
<span>Runtime contracts</span>
<small>The wire-shape walkthrough behind these schemas.</small>
</a>

<a href="../../adr/receipts-and-handoffs-as-public-contracts/">
<strong>ADR</strong>
<span>0005 · Receipts &amp; handoffs as public contracts</span>
<small>Why these contracts are versioned and safe to cite.</small>
</a>

<a href="../cli/">
<strong>Reference</strong>
<span>CLI</span>
<small>Inspect schemas via the <code>craik schema</code> command.</small>
</a>

</div>
