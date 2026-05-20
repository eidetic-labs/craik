# Craik

Craik is a governed agent-runtime substrate: typed case files, policy envelopes,
capability receipts, prompt compilation, pluggable provider transports, handoffs,
and work graphs for durable project work.

The project is named after Kenneth Craik, whose work on mental models framed intelligence as the ability to build internal representations of the world and use them to reason before acting. Craik applies that idea to agent systems: agents should not operate as isolated prompt executions. They should work from shared, evidence-backed project models, leave durable handoffs, and act inside explicit governance boundaries.

## Thesis

Most agent frameworks optimize for tool calling, prompt routing, or parallel execution. Those are necessary, but they are not enough for long-running work.

Craik is built around a different premise:

> Agent systems become useful at organizational scale when they can remember, justify, coordinate, dispute, and hand off work over time.

Craik treats memory, provenance, policy, and work state as runtime concerns rather than optional logging.

## What Works Today

Craik can assemble local repository context, read optional GitHub and Stigmem
state, compile governed runner prompts, execute fixture-backed and live-shaped
provider requests through OpenAI Responses, Anthropic Messages, and
OpenAI-compatible Chat Completions adapters, persist receipts/handoffs/work
graphs, consume completed handoffs into follow-up governed runs, and propose
memory updates for review.
Provider-backed runs can also be dispatched through v0.3.0 specialist roles
such as verifier, docs reviewer, policy reviewer, memory curator, and
adjudicator.
Multi-agent coordination now has a typed, receipt-backed mailbox contract for
agent-to-agent messages linked to task, run, handoff, and role identities.
Concurrent runs against the same project are checked against active intent-lock
scopes before new loop phases or tool dispatch, with overlaps recorded as
coordination denial receipts.
Structured debates can now capture role-linked positions, preserve minority
claims and evidence, and resolve through an adjudication receipt or human
delegation receipt.
Cross-agent reviews can request bounded review of another agent's worker
result, handoff, or debate summary and complete with typed findings without
mutating the reviewed artifact.
Human delegation can pause a run with a receipted request, record an accepted,
rejected, or cancelled operator response, and then resume from the interrupted
run boundary.
Scope-change handling now prevents silent expansion: discovered work outside the
active intent lock interrupts the run, persists the proposed scope change, and
requires an explicit expand, sibling-work, handoff, or denial decision.
The work graph is also becoming live coordination state: v0.3.0 mailbox,
review, debate, delegation, and scope-change artifacts persist graph events that
operators can query before a final export.

The live provider path is explicit. Runtime callers opt into live access, supply
provider metadata, and resolve credentials through typed credential profiles or
credential pools. The local OpenAI-compatible provider path can target a
localhost `/v1` server such as Ollama for optional live validation without paid
API keys.

Craik authenticates to provider APIs through typed credential profiles. Profile
kinds include env-var API keys, local-CLI OAuth fallback (e.g. reading
`~/.claude/.credentials.json`), vendor CLI subprocess bridges, external secret
manager references, and Stigmem-backed credential references. A credential pool
supports rotation and failover across multiple profiles.

Craik authenticates the operator via OIDC against any compliant IdP. Device-code
and loopback+PKCE flows are both supported; `craik login` initiates the flow,
`craik whoami` reports the active operator, `craik logout` revokes the session.
Every provider call is bound to both an operator identity and a credential
identity; every receipt names both. Workload-identity providers (GitHub Actions,
Kubernetes projected tokens, generic file/env-var) plus RFC 8693 token exchange
enable credential-less deployment in CI and cloud.

Policy envelopes can constrain which operators and which credentials a task may
use. First-time use of a credential profile is approval-gated and produces a
receipted authorization chain. Credential expiry surfaces as evidence in case
files so long-running runs are warned about tokens that will expire mid-work.

Durable execution continuity is now part of the runtime. Provider-backed runs
record phase idempotency keys and can resume from completed phase boundaries.
The loop enforces wall-clock budgets, provider token budgets, and pre-dispatch
time checks before producing additional side effects.

Configured shell tool calls can execute through the local-process sandbox
backend for registered command references. Dispatched tool results are
attested, cancellation propagates into in-flight local processes, and run
recovery commands expose persisted run state, cancellation, resume, and run
delta views. Local-store schema changes are applied through a registered,
forward-only migration framework.

## What Does Not Work Yet

Craik is not yet a fully autonomous release-quality agent. It does not claim
unbounded tool execution, unattended file edits, broad remote Stigmem writes, or
production multi-agent orchestration. Tool execution is policy-bound and
currently limited to configured local-process sandbox execution for registered
command references; container, remote-shell, browser, and MCP execution
backends remain future work. Live provider calls remain opt-in rather than
hidden CI behavior.

## Vision

The long-term direction is a durable agent operating layer where agents work
from shared project state, leave auditable handoffs, resolve contradictions, and
coordinate across memory, policy, tools, issues, and release workflows.

## Relationship to Stigmem

Craik is a separate product and repository from Stigmem.

- Stigmem is the durable memory and truth substrate: facts, provenance, scopes, trust, federation, auth, and plugin hooks.
- Craik is the agent operating layer: orchestration, context assembly, handoffs, work graphs, capability policy, receipts, and user workflows.

Craik can run in degraded local mode without Stigmem for demos and development, but Stigmem is the reference substrate for real team use.

## Agent Integration Model

Craik core is runner-agnostic. The current MVP path provides deterministic
OpenAI- and Anthropic-shaped provider runner execution for certification and
offline validation. Preview prompt-handoff adapters are also available for:

- Codex
- Claude
- Gemini

Each runner path consumes the same Craik contracts: project case file, policy
envelope, capability grants, worker result, receipts, handoff, and memory
proposals.

Craik is not built as a dependency layer on another agent framework. It borrows broadly useful product patterns such as gateway ergonomics, workspace identity, persistent sessions, typed tools, skills, and channel integrations while keeping Craik's first agent path focused on direct runner adapters.

## Core Ideas

- **Shared project models:** Agents receive a task-specific model of the project before acting.
- **Durable handoffs:** Agent runs end with machine-readable state for the next agent.
- **Fact-grounded context:** Context is assembled from evidence, ADRs, repo state, issues, docs, and memory.
- **Governed execution:** Tool access, write authority, review gates, and documentation obligations are policy-controlled.
- **Capability receipts:** Important actions produce structured records of actor, target, reason, and result.
- **Contradiction handling:** Conflicting facts are surfaced for resolution instead of silently overwritten.
- **Work graph:** Tasks, PRs, issues, facts, decisions, docs, tools, agents, and artifacts are modeled as connected state.

## Planning Docs

- [Documentation Index](docs/index.md)
- [Vision](docs/vision.md)
- [Architecture Decisions](docs/adr/0001-record-mvp-runner-scope.md)
- [Product Strategy](docs/product-strategy.md)
- [Differentiators](docs/differentiators.md)
- [Architecture](docs/architecture.md)
- [Runtime Contracts](docs/runtime-contracts.md)
- [Case Files](docs/concepts/case-files.md)
- [Project Model](docs/concepts/project-model.md)
- [Governance](docs/concepts/governance.md)
- [Intent Locks](docs/concepts/intent-locks.md)
- [Handoffs](docs/concepts/handoffs.md)
- [Receipts](docs/concepts/receipts.md)
- [Feature Specification](docs/features.md)
- [MVP Plan](docs/mvp.md)
- [Implementation Plan](docs/implementation-plan.md)
- [Roadmap](docs/roadmap.md)
- [Governance Model](docs/governance.md)
- [Stigmem Integration](docs/stigmem-integration.md)
- [Installation](docs/guides/installation.md)
- [Quickstart](docs/guides/quickstart.md)
- [Configuring Craik Home](docs/guides/configuring-craik-home.md)
- [Project Registry](docs/guides/project-registry.md)
- [Using Case Files](docs/guides/using-case-files.md)
- [Agent Onboarding](docs/guides/agent-onboarding.md)
- [GitHub Adapter](docs/guides/github-adapter.md)
- [Stigmem Documentation Demo](docs/guides/stigmem-docs-demo.md)
- [Work Graph](docs/concepts/work-graph.md)
- [Scope Control](docs/guides/scope-control.md)
- [Writing Handoffs](docs/guides/writing-handoffs.md)
- [Memory Proposals](docs/guides/memory-proposals.md)
- [Memory Diffs](docs/guides/memory-diffs.md)
- [Memory Impact Preview](docs/guides/memory-impact-preview.md)
- [Contradiction Inbox](docs/guides/contradiction-inbox.md)
- [Connecting Stigmem](docs/guides/connecting-stigmem.md)
- [Evidence And Assumptions](docs/guides/evidence-and-assumptions.md)
- [Context Budgeting](docs/guides/context-budgeting.md)
- [Development Checks](docs/guides/development.md)
- [CLI Reference](docs/reference/cli.md)
- [Schema Reference](docs/reference/schemas.md)
- [Policy Profiles](docs/reference/policy-profiles.md)
- [Memory Backends](docs/reference/memory-backends.md)
- [Memory And Stigmem](docs/concepts/memory-and-stigmem.md)
- [Stigmem Compatibility](docs/reference/stigmem-compatibility.md)
- [Fail-Open](docs/guides/fail-open.md)
- [Capability Grants](docs/guides/capability-grants.md)
- [Running Policy Tests](docs/guides/running-policy-tests.md)
- [Redaction](docs/reference/redaction.md)
- [Local State Layout](docs/reference/local-state.md)
- [Local Store](docs/reference/local-store.md)
- [Config Reference](docs/reference/config.md)
- [Project Profile](docs/reference/project-profile.md)
- [Policy Tests](docs/reference/policy-tests.md)
- [GitHub Config](docs/reference/github-config.md)
- [Graph Export](docs/reference/graph-export.md)
- [Self-Audit](docs/reference/self-audit.md)
- [Secrets](docs/security/secrets.md)
- [Limitations](docs/limitations.md)

## Current Status

Craik is moving toward a robust `0.x.0` MVP release. `1.0.0` is a later
stability signal, not the first release target.

The repository now includes the CLI package, strict runtime contracts, local
SQLite state, project/task/case-file workflows, policy and receipt primitives,
runner preview contracts, governed provider-backed loops, durable run
continuity, budget enforcement, local-process sandboxed shell dispatch,
multi-agent review contracts, instruction distillation, quality/recovery
helpers, skills/plugins foundations, operator view formatters,
gateway/channel contracts, sandbox/provider routing contracts, learning-loop
helpers, multimodal decisions, migration/i18n contracts, and broad docs/tests
through the v0.12 roadmap.

The remaining MVP work is to harden these contract and helper surfaces into one
complete release-quality workflow: remote Stigmem write promotion,
God-file/runtime package cleanup, ADR-backed design decisions, and docs/test
depth comparable to Stigmem. Package version `0.2.0` marks the durable
execution continuity gate after the first governed provider, credential, and
operator-identity substrate; roadmap sections remain implementation gates, not
`1.0.0` readiness claims. See
[Robust MVP Roadmap](docs/mvp-roadmap.md).

## Implementation Stack

Craik core is implemented in Python 3.12+ with a CLI-first package shape. The initial stack is:

- Python 3.12+
- Typer for CLI
- Pydantic for runtime contracts
- SQLite for local persistent state
- stdlib HTTP for the first Stigmem and GitHub compatibility clients
- `pytest` for tests
- `ruff` and `mypy` for quality gates

TypeScript remains appropriate for future UI, gateway adapters, and channel integrations, but it is not the initial core runtime stack.

## Package and CLI Naming

Craik uses the same name across the public repository, Python package, import module, and CLI command:

- GitHub repository: `eidetic-labs/craik`
- PyPI distribution: `craik`
- Python module: `craik`
- CLI command: `craik`
- Future npm package, if needed: `craik`

Live registry checks on 2026-05-15 showed `craik` available on both PyPI and npm. If a registry race occurs before publication, `craik-runtime` is the fallback distribution name while preserving `craik` as the CLI command and Python module.

## Local State

Craik uses a single product-home directory by default:

```text
~/.craik/
```

The location can be overridden with:

```text
CRAIK_HOME=/custom/path
```

Craik should keep different data classes separated inside that home:

```text
~/.craik/
  config/
  secrets/
  state/
  cache/
  logs/
  receipts/
  handoffs/
  case-files/
  projects/
```

Project-local `.craik/` directories are opt-in only. Craik should not silently create project-local metadata inside repositories.

## License

Craik is released under the [MIT License](LICENSE). The license choice is intended to match the permissive adoption pattern used by comparable agent frameworks while keeping Eidetic Labs trademarks and branding separate from the code license.

## Project Governance

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Security disclosure: [SECURITY.md](SECURITY.md)
- Trademark and brand usage: [TRADEMARKS.md](TRADEMARKS.md)
- Maintainer and release policy: [MAINTAINERS.md](MAINTAINERS.md)

## Initial Build Target

The first implementation should focus on a repository-aware CLI runtime:

1. Create a project profile for a local Git repository.
2. Connect optional Stigmem memory.
3. Assemble a task case file from repository state, docs, issues, policies, and facts.
4. Execute a governed single-agent task with scoped capabilities.
5. Record capability receipts.
6. Produce a structured handoff.
7. Propose fact updates for future agents.

Multi-agent orchestration, work graph visualization, contradiction inbox, and plugin probation should be layered on after the single-agent durable workflow is working end to end.

## First Demo Target

Craik's first real demo target is Stigmem documentation and state reconciliation. The initial runnable version is exposed through `craik demo stigmem-docs`.

The demo should:

1. Register the Stigmem repository as a Craik project.
2. Connect to a local Stigmem node.
3. Create a docs reconciliation task.
4. Assemble a case file from repository state, ADRs, public docs, GitHub issues/PRs, recent Stigmem facts, and prior handoffs.
5. Identify stale or contradictory documentation.
6. Produce proposed documentation updates.
7. Record capability receipts for important actions.
8. Generate a durable handoff.
9. Propose or write new Stigmem facts.
10. Export a work graph for the task.

This target is intentionally based on a real workflow that already exposed the need for durable memory, public/internal doc boundaries, ADR constraints, and agent handoffs.
