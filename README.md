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

Note: v0.12.1 supersedes v0.12.0. Operators on v0.12.0 should upgrade;
v0.12.0 shipped with an auth-UX gap that prevented `craik chat` from working
in default installs.

Craik can assemble local repository context, read optional GitHub and Stigmem
state, compile governed runner prompts, execute fixture-backed and live-shaped
provider requests through OpenAI Responses, Anthropic Messages, and
OpenAI-compatible Chat Completions adapters, persist receipts/handoffs/work
graphs, consume completed handoffs into follow-up governed runs, and propose
memory updates for review.
Provider-backed runs can also be dispatched through specialist roles such as
verifier, docs reviewer, policy reviewer, memory curator, and adjudicator.
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
The work graph also acts as live coordination state: mailbox, review, debate,
delegation, and scope-change artifacts persist graph events that operators can
query before a final export.
Handoff consumers must now make their credential and operator assignment
explicit. Craik rejects accidental producer-identity reuse unless the caller
passes an explicit continuation flag, and the assignment is recorded as a
receipt on the follow-up run.

The live provider path is explicit. Runtime callers opt into live access, supply
provider metadata, and resolve credentials through typed credential profiles or
credential pools. The local OpenAI-compatible provider path can target a
localhost `/v1` server such as Ollama for optional live validation without paid
API keys.

## Getting Started

```bash
pip install craik
craik auth login openai
craik model set openai/gpt-4o-mini
echo "summarize the README" | craik chat -q -
```

That is the single-operator happy path. Use `anthropic`, `gemini`, or `local`
instead of `openai` when configuring another provider. See
[installation](docs/guides/installation.md) and
[quickstart](docs/guides/quickstart.md) for the full operator walkthrough.

## Operator Modes

Craik runs in one of two modes:

**Single-operator local (default).** Provider credentials plus an active model
unlock the chat surface. Run `craik auth login <provider>`, then
`craik model set <provider/model>`, then `craik chat`. No OIDC identity
provider is required.

**Audited multi-operator (opt-in).** Set `CRAIK_OPERATOR_REQUIRED=1` to require
an OIDC-attested operator session in addition to provider credentials.
`craik login` starts the device-code or loopback+PKCE flow; `craik whoami`
reports the active operator; `craik logout` revokes the session. This mode is
for teams, regulated deployments, and workload-identity CI.

Craik authenticates to provider APIs through typed credential profiles. Profile
kinds include env-var API keys, local-CLI OAuth fallback (e.g. reading
`~/.claude/.credentials.json`), vendor CLI subprocess bridges, external secret
manager references, and Stigmem-backed credential references. A credential pool
supports rotation and failover across multiple profiles.

In audited multi-operator mode, provider calls are bound to both an operator
identity and a credential identity; receipts name both. Workload-identity
providers (GitHub Actions, Kubernetes projected tokens, generic file/env-var)
plus RFC 8693 token exchange enable credential-less deployment in CI and cloud.

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
command references. Live provider calls remain opt-in rather than hidden CI
behavior.

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

Craik core is runner-agnostic. It provides deterministic OpenAI- and
Anthropic-shaped provider runner execution for certification and offline
validation. Prompt-handoff adapters are also available for:

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

## Implementation Stack

Craik core is implemented in Python 3.12+ with a CLI-first package shape. The
stack is:

- Python 3.12+
- Typer for CLI
- Pydantic for runtime contracts
- SQLite for local persistent state
- stdlib HTTP for the first Stigmem and GitHub compatibility clients
- `pytest` for tests
- `ruff` and `mypy` for quality gates

## Package and CLI Naming

Craik uses the same name across the public repository, Python package, import module, and CLI command:

- GitHub repository: `eidetic-labs/craik`
- PyPI distribution: `craik`
- Python module: `craik`
- CLI command: `craik`

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
