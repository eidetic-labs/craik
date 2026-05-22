# Changelog

All notable Craik release changes are tracked here. Craik's first public
release target is a robust `0.x.0` MVP; `1.0.0` remains a later compatibility
signal after real-world usage and security soak.

This project follows the shape of Keep a Changelog and uses semantic versioning
within the `0.x.0` stability expectations described in
`docs/guides/release-management.md`.

## Unreleased

### Added

- v0.7.0 read-only operator surface overview through `craik operator
  overview`, with project scoping, JSON output, section navigation,
  local-store counts, and CLI-first operator surface documentation.
- Read-only work graph explorer through `craik operator work-graph`,
  with terminal formatting for nodes and edges plus JSON output for
  tooling.
- Read-only handoff viewer through `craik operator handoff`, accepting
  handoff ids or task ids and preserving the durable-summary redaction
  boundary.
- Read-only receipt viewer through `craik operator receipt`, covering
  capability and plugin receipt records with text and JSON output.
- Read-only contradiction inbox through `craik operator contradictions`,
  with task and status filters plus text and JSON output.
- Read-only evidence and assumption view through `craik operator
  evidence`, keeping assumptions visually separate from evidence with
  task filtering and JSON output.
- Read-only delegation queue through `craik operator delegations`,
  with task and status filters for human delegation points.
- Read-only budget/quota view through `craik operator budget`, making
  missing persisted cost, token, request, and quota data explicit.
- Read-only instruction distillation view through `craik operator
  instructions`, showing sources, snapshots, provenance, proposals,
  and promotion reviews without mutating authority.
- Read-only quality gate view through `craik operator quality`,
  summarizing handoff scores, evidence scores, critic findings, and
  red-team findings with text and JSON output.
- Read-only memory impact preview view through `craik operator
  memory-impact`, preserving the boundary between proposals, facts to
  add, facts to invalidate, evidence gaps, and contradiction risks.
- Read-only known traps view through `craik operator traps`, exposing
  known traps and negative knowledge with project/task filters and
  timestamped JSON output.
- Read-only run delta view through `craik operator run-delta` and
  `craik operator run-deltas`, resolving delta, run, or task IDs and
  showing linked recovery sessions.
- v0.7.0 release-readiness and documentation assessment, recording
  completed operator-experience goals and no known release blockers.

## 0.6.0 — 2026-05-21

### Added

- v0.6.0 skill ecosystem contracts for semantic skill packages,
  project/global skill registries, package-level context requirements,
  and redacted skill invocation contexts.
- Governed plugin ecosystem contracts for plugin descriptors,
  probation records, least-privilege plugin capability grants, plugin
  receipts, adapter packages, and reference integrations.
- Community skill and plugin guides covering authoring, scope, review,
  installation boundaries, grants, receipts, adapters, and security
  expectations.
- v0.6.0 release-readiness documentation with goal issue status,
  validation commands, security notes, blocker state, and release
  automation hygiene.

### Changed

- Skill packages now require expected input schemas to be declared as
  context requirements, including trust boundary and missing-context
  behavior.
- Skill registries now require every active entry to appear in
  `active_entry_ids` and reject inactive entries in precedence order.
- Plugin and adapter compatibility versions now use semantic-version
  validation for deterministic release and runtime comparisons.
- Release automation now accepts changelog release headings that use an
  em dash, en dash, or ASCII hyphen between version and date.

### Security

- Plugin descriptors declare trust boundaries and grant-required
  capabilities must name concrete operations and targets.
- Plugin probation promotion now requires evidence-backed criteria and
  decisions before durable trust can be granted.
- Plugin capability grants reject ambient operations such as `*` or
  `all`, require scoped targets, and expose a current-operation
  authorization helper.
- Plugin receipts reject unredacted result metadata and preserve
  probation links while a plugin is under review.

## 0.5.0 — 2026-05-21

### Added

- v0.5.0 quality and continuity contracts for recovery sessions, run
  deltas, runtime critic findings, red-team findings, handoff quality
  scores, evidence coverage scores, context debt, tool-result
  attestations, knowledge freshness probes, known traps, negative
  knowledge, scratchpad records, unknowns, context requests, and agent
  exit-discipline checks.
- Recovery and delta operator paths through `craik run recover` and
  `craik run delta`, backed by durable local-store records.
- Production capture paths and CLI commands for scratchpad records,
  unknowns, context requests, known traps, negative knowledge,
  runtime critic findings, and red-team findings.
- Receipt-linked resolution paths and CLI commands for unknowns,
  context requests, and context debt.
- v0.5.0 capture-layer end-to-end coverage that validates persisted
  continuity records flow into case files, handoffs, quality scores,
  and exit-discipline enforcement.
- Operator view formatting for quality gates, known traps and negative
  knowledge, run deltas, recovery sessions, scratchpad/unknown state,
  context requests, and exit-discipline status.
- v0.5.0 release-readiness documentation with goal issue status,
  validation commands, security notes, and pre-release blocker state.

### Changed

- Case-file and handoff continuity flows now surface known traps,
  negative knowledge, scratchpad records, unresolved unknowns,
  context requests, context debt, freshness warnings, and recovery
  state as structured runtime records rather than prose-only notes.
- Handoff creation now persists handoff quality and evidence coverage
  scores, and blocks incomplete exits unless an explicit blocked-exit
  override rationale is recorded.
- The goal workflow now requires pushed PRs, green required checks,
  agent-owned merge of clean PRs, and stale branch pruning before moving
  to the next goal.

### Security

- Runtime critic and red-team findings remain non-authoritative until a
  reviewer acts on them, preventing review output from becoming hidden
  policy or privileged instruction text.
- Tool-result attestations and freshness probes distinguish observed
  outputs from stale, missing, or unverified summaries before reuse.
- Tool-result attestations and recovery sessions now carry local HMAC
  integrity metadata and are verified on read from the local store.
- `craik run recover` and `craik run delta` now require an active
  operator session before exposing recovery state for existing runs or
  deltas.
- Scratchpad notes require expiry, and negative knowledge requires
  evidence and explicit scope so temporary or absence-based claims do
  not silently become durable project truth.
- Resolved unknowns, fulfilled context requests, and resolved context
  debt must link the operator receipt that closed the record.

## 0.4.0 — 2026-05-21

### Added

- Instruction source registration: projects can register declared instruction
  files with typed source metadata, path-bound registry records, and
  receipt-backed local-store persistence before ingestion.
- Declared instruction ingestion: Markdown, Cursor rules, Codex, Copilot, and
  policy document sources are parsed from project-confined paths into
  candidate instruction statements.
- Source snapshot refresh: registered files are hashed with normalized
  newlines, tracked as `new` / `unchanged` / `changed` / `missing`, and used to
  mark derived distillations stale when source text changes or disappears.
- Line/range provenance: extracted instruction candidates retain deterministic
  source snapshot links, line and column ranges, summaries, and excerpt hashes.
- Instruction categorization: provenanced statements become persisted
  distillation proposals with category traceability and warnings for
  unclassified candidates.
- Inter-source contradiction reports: normalized policy, boundary, command,
  instruction, and security-rule proposals now surface cross-source conflicts
  while ignoring same-source and stale deferred items.
- Operator approval receipts: proposed distillations become governing
  constraints only through explicit approve decisions, and reject decisions are
  recorded with receipts.
- Distillation CLI: `craik instructions register`, `ingest`, `list`,
  `approve`, `reject`, and `show` expose registration, pipeline execution,
  review, decisions, and provenance inspection through the active operator
  session.
- Instruction distillation documentation: operators now have reference pages
  for sources, distilled proposal lifecycle, approval reviews, and an
  end-to-end management guide for the `craik instructions` workflow.
- v0.4.0 release readiness documentation now records the instruction
  distillation sign-off, verification commands, and security notes before
  release prep.

### Changed

- Case files now include governing distillations as deterministic
  `distillations` evidence with category, source, provenance ranges, and
  approval receipt snapshots.
- Compiled prompts now include one authoritative `Active instruction
  constraints` section for governing distillations, sorted by category, source
  ID, and sanitized literal statement text with provenance annotations and
  stale-exclusion warnings.

### Security

- Stale or contradicted distillation approvals now require an explicit operator
  override rationale, and review receipts record whether stale or contradiction
  overrides were used.
- Instruction approval receipts now carry integrity HMACs, and active runtime
  consumers exclude governing constraints whose approval receipt is missing or
  fails verification.
- Direct instruction approval API calls now require an active operator session
  unless a caller explicitly opts into unbound approval for test or controlled
  internal use; operator-check failures now expose typed error codes and emit
  hashed structured audit-hook fields for session failures.
- Instruction source registration now rejects absolute paths, parent-directory
  escapes, and symlink escapes before a source enters the registry.
- Oversize instruction sources and sources exceeding the aggregate project
  source budget are skipped during snapshot refresh and excluded from proposal
  ingestion instead of being read without bounds.
- GitHub Actions workflows now pin third-party actions to immutable SHAs, and
  the publish workflow emits package provenance attestations before upload.

## 0.3.0 - 2026-05-20

### Added

- Handoff consumption workflow: `craik task resume --from-handoff` now creates
  a follow-up task, case file, and pending run that record source handoff
  provenance while requiring an explicit consumer credential and operator
  identity.
- Role-based provider dispatch: `craik run execute --role` now records a
  policy-checked specialist role assignment, dispatch receipt, and run-level
  role metadata.
- Receipt-backed `craik agent-message` CLI and local-store helpers for sending
  and receiving authenticated typed multi-agent messages linked to tasks, runs,
  handoffs, and roles.
- Intent-lock coordination for simultaneous runs: overlapping active scopes on
  the same project now block before new loop phases or tool dispatch and
  persist a denial receipt.
- Structured debate runtime helper that creates role-linked debate turns,
  summarizes agreement or disagreement, and resolves by adjudication receipt
  or human-delegation receipt.
- Cross-agent review protocol helper that creates receipted review requests
  for worker results, handoffs, or debate summaries and completes them with
  typed findings linked to reviewed artifacts.
- Human delegation pause/resume workflow: runs can be interrupted with
  receipted delegation requests, resolved or cancelled by CLI, and resumed from
  the recorded response.
- Scope-change protocol: discovered work outside the current intent lock now
  interrupts the run, records a scope-change request receipt, and exposes
  `craik scope-change decide` for explicit expand, sibling-task, handoff, or
  denial decisions before continuing.
- Live work graph coordination: mailbox messages, reviews, debates,
  delegations, and scope-change artifacts now persist work-graph events that can
  be queried as active coordination state.
- Per-agent identity isolation: consuming a handoff now records an explicit
  consumer credential/operator assignment, rejects producer identity reuse by
  default, and requires an explicit continuation flag plus rationale when reuse
  is intentional.

### Security

- Delegation resolution now requires resolver operator identity and rejects
  attempts to resume a paused run opened by another operator.
- Mailbox sends authenticate `from_agent` against the sender run's role state
  before storing the message or receipt.
- Role dispatch now requires explicit role allowlists and gates runner
  overrides behind the `role.runner.override` policy capability.
- Mailbox message bodies are bounded and repeated same-subject messages receive
  unique IDs instead of overwriting the latest message.

## 0.2.0 - 2026-05-20

### Added — Resumable execution

- Durable run phase idempotency with completed step keys, stable runner step
  context keys, and resume behavior that skips already captured phase outputs.
- Operator-facing recovery commands: `craik run show`, `craik run resume`, and
  `craik run cancel` for persisted provider-backed runs.

### Added — Budgets at execution boundaries

- Per-run wall-clock budgets that interrupt before the next phase or provider
  tool round when the budget is exhausted.
- Provider token budget accounting that decrements from usage metadata and
  blocks additional provider calls after exhaustion.
- Pre-dispatch budget checks that stop expired runs before side effects,
  receipts, or tool-result attestations are produced.

### Added — Sandboxed tool execution

- Local-process sandbox backend for registered shell command references, routed
  through governed loop tool dispatch when configured.
- Cancellation propagation into in-flight local-process sandbox commands, with
  cancelled results replayed through tool messages.
- Tool-result attestations that hash the redacted replay payload and link each
  dispatched result to its side-effect receipt.

### Added — Recovery and observability

- Persisted exit-discipline checks at the handoff boundary, including blocking
  reasons for incomplete handoffs.
- `craik run delta` for rendering persisted run-delta records and linked
  recovery sessions as operator views or JSON.

### Added — Storage

- Registered, forward-only local-store migration runner that preserves existing
  migrations and adds framework metadata migration coverage.

## 0.1.2 - 2026-05-18

### Fixed

- Restored Python 3.14 compatibility for normal installs by upgrading Pydantic
  to `2.13.4`, which depends on a `pydantic-core` release with Python 3.14
  wheels.
- Restored package metadata to `requires-python >=3.12` and reverted the
  temporary Python 3.12/3.13-only install guidance from `0.1.1`.

## 0.1.1 - 2026-05-18

### Fixed

- Restricted package metadata to Python 3.12 and 3.13 so `pipx install craik`
  does not select Python 3.14, where the current Pydantic runtime dependency
  cannot build compatible wheels.
- Updated installation and development docs to call out the Python 3.12/3.13
  support window and the `pipx --python` install path.
- Generalized the publish workflow tag guard so patch releases are checked
  against their own immutable version tag instead of being hardcoded to
  `v0.1.0`.

## 0.1.0 - 2026-05-17

### Added

- Live provider transport path with stdlib HTTP, explicit live access, retries,
  cancellation, streaming callback capture, and recorded chat-completions
  integration coverage.
- Provider adapters for OpenAI Responses, Anthropic Messages, and
  OpenAI-compatible Chat Completions, including local `/v1` provider metadata.
- Secret reference resolution for provider credentials without storing raw
  secret material in transport instances.
- Governed loop support for dispatchable provider tool calls and replayable
  streaming output chunks.

### Added — Pluggable credential sources

- Typed credential abstraction with `auth-profiles.json` and
  `<provider_family>:<name>` profile IDs.
- Credential sources: env-var API key, local-CLI OAuth fallback (e.g. Claude
  Code credentials), vendor-CLI subprocess bridge, external secret manager
  references, markers, and Stigmem-backed credential references.
- Credential pool with rotation, failover, and per-profile health tracking.
- Credential CLI: `craik auth list / add / remove / test / status / approve /
  grant`.
- Credential health surfaced in `craik doctor`.

### Added — OIDC operator identity

- OIDC operator authentication with device-code and loopback+PKCE flows.
- IdP discovery, JWKS-validated ID tokens (rejects `alg=none`, unknown `kid`,
  asymmetric/symmetric algorithm confusion), and refresh-token handling.
- Operator session store at `<CRAIK_HOME>/operator-session.json` with
  `craik login`, `craik logout`, `craik whoami`.
- Workload identity providers: GitHub Actions, Kubernetes projected service
  account token, generic file token, env-var token.
- RFC 8693 token-exchange secret manager for federated credential brokering.
- Operator identity bound to every provider call and persisted on every
  receipt.

### Added — Governance-native credential features

- Credential-scoped receipt fields: `auth_profile_id`, `auth_kind`,
  `auth_identity_hash`.
- Operator-scoped receipt fields: `operator_subject`, `operator_issuer`,
  `operator_email`, `operator_groups`.
- Policy envelopes can constrain operators (`required_operator`,
  `allowed_operator_groups`, `allowed_operator_subjects`,
  `required_operator_issuer`) and credentials (`allowed_credential_kinds`,
  `allowed_credential_profiles`).
- Approval-gated first live use of any credential profile, recorded as a
  receipt.
- Operator-credential authorization binding with a receipted grant chain.
- Credential expiry surfaced as evidence/risk in case files for long-running
  work.
- Per-credential redaction patterns extending the global redaction utility.
- Per-agent credential and operator isolation in handoff records (foundation
  for v0.3.0 multi-agent runtime).

## 0.0.0 - 2026-05-16

### Added

- Initial pre-release package metadata.
- Local CLI entrypoint and source-tree installation path.
