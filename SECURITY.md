# Security Policy

Craik is pre-release software. Security-sensitive behavior should be designed conservatively because the runtime is expected to interact with agents, tools, shell commands, Git repositories, GitHub, secrets, and Stigmem memory.

## Supported Versions

Craik has no supported release line yet.

| Version | Supported |
| --- | --- |
| pre-0.1.0 | No formal support; best-effort private disclosure |

This table should be updated when the first package release is published.

## Reporting a Vulnerability

Do not open public GitHub issues for security vulnerabilities.

Report privately to:

security@eideticlabs.ai

Include:

- affected version or commit,
- environment,
- reproduction steps,
- expected impact,
- whether secrets, tokens, repositories, or memory facts may be exposed,
- and any suggested mitigation.

## Expected Response

Until Craik has a staffed security process, response is best effort. The intended target process is:

- acknowledge within 5 business days,
- assess severity and scope,
- coordinate a fix privately when appropriate,
- credit reporters when requested and appropriate,
- and publish advisories for released versions when needed.

## Security-Sensitive Areas

Please report issues involving:

- command execution,
- file write boundaries,
- GitHub write operations,
- token or API key handling,
- memory scope leaks,
- Stigmem fact visibility,
- prompt or context injection that bypasses policy,
- capability grant bypass,
- receipt redaction failures,
- plugin sandbox failures,
- and unsafe default configuration.

## Runtime Instruction Distillation Trust Model

Craik treats declared instruction files as content-untrusted evidence.
Anyone who can change a registered source file can propose runtime
constraints, but those proposals do not become authority until an
operator approves them.

- `~/.craik/` must be private to the operator account. Shared write
  access to the local store, operator session, or receipt files is a
  full compromise of local audit integrity.
- Registration is explicit and project-confined. Absolute paths,
  parent-directory escapes, and symlink escapes are rejected before a
  source enters the instruction registry.
- Ingestion refreshes source snapshots, defers stale proposals, and
  opens contradiction reports before review.
- Approval is the authority boundary. Governing constraints require an
  operator approval receipt, and stale or contradicted approvals require
  explicit override rationale.
- Approval receipts carry an integrity HMAC backed by an owner-only
  local secret under Craik home. Case files, onboarding context,
  handoffs, and compiled prompts exclude governing constraints whose
  approval receipt is missing or fails verification.
- On POSIX systems Craik sets owner-only permissions on local secrets and
  session files. Windows support currently relies on the default user
  profile ACLs; if Windows becomes a first-class target, Craik should add
  explicit ACL hardening and validation for these files.
- Compiled prompts render approved instruction text as sanitized
  single-line literal content inside the `Active instruction
  constraints` section to reduce prompt-injection risk from registered
  source files.

## v0.5.0 Runtime Continuity Trust Model

Craik treats quality, recovery, and continuity records as evidence and
operator-visible signals, not as authority. These records can guide an
agent or reviewer, but they do not approve policy changes, promote
memory, or prove external truth by themselves.

- Runtime critic and red-team findings are non-authoritative until a
  reviewer adjudicates them. Findings can block operator workflows, but
  they must not become hidden privileged instructions.
- Scratchpad records expire by design. Durable project memory still
  requires the normal memory proposal and approval flow.
- Unknowns and context requests are first-class blocking state. Handoff
  creation blocks when unresolved unknowns or open context requests
  remain unless the caller records an explicit blocked-exit override
  rationale.
- Unknown, context-request, and context-debt resolution paths require
  receipt linkage. Operators can resolve these records through the
  `craik knowledge resolve-unknown`, `fulfill-context-request`, and
  `resolve-context-debt` commands; direct runtime callers receive the
  same receipt-linked state transition helpers.
- Negative knowledge requires evidence and scope. When it contradicts a
  positive assertion, Craik opens a contradiction record instead of
  silently deleting or replacing the existing assertion.
- Tool-result attestations and recovery sessions carry local HMAC
  integrity metadata and are verified on read. This protects local audit
  continuity against accidental or unsophisticated tampering, but it is
  not a substitute for OS account isolation or a tamper-resistant remote
  audit log.
- `craik run recover` and `craik run delta` require an active operator
  session before returning existing recovery state. Missing identifiers
  may still return a not-found error without revealing state.

## v0.6.0 Skills and Plugin Trust Model

Craik separates reusable skills from runtime plugins. Skill packages
describe reusable context and entrypoints, but they do not carry runtime
authority. Plugin descriptors declare capability needs, and runtime
authority is granted only through live plugin capability grants.

- Plugin operations must be authorized at execution time against the
  current local store state. A cached grant decision is not authority.
- Probation is a hard gate. A plugin with a latest probation record that
  has not granted durable trust is denied even when a matching capability
  grant exists.
- Capability grants use strict expiry boundaries. A grant is invalid at
  exactly `expires_at` and after it.
- Plugin probation and plugin receipt records carry local HMAC integrity
  metadata and are verified on read. Existing unsigned records remain
  readable for compatibility, but newly written records are signed.
- Plugin receipt creation should go through the runtime receipt factory,
  which redacts result summaries and metadata before persistence.
- Skill registry source paths are confined to relative paths and reject
  absolute paths or parent-directory traversal.
- Skill, plugin, adapter, and reference docs links allow safe relative
  documentation paths, HTTPS URLs, and localhost HTTP for development.
  Other URL schemes are rejected.

## v0.7.0 Operator Experience Trust Model

Craik treats the operator surface as a read-only inspection layer over
local project state, not as a bypass around runtime authority or
operator identity. Operator commands must prove the caller is bound to
an active local operator session before reading persisted state.

- Every `craik operator` command that reads local-store state requires
  an active operator session. Missing sessions fail before project,
  task, receipt, delegation, contradiction, quality, or continuity
  records are returned.
- Multi-project homes require an explicit `--project` scope for
  unscoped list views. Single-project homes auto-scope to that project,
  and empty homes preserve the existing empty-view behavior.

## v0.12.3 Terminal Shell Mode Trust Model

Craik's TUI `!`-prefix shell mode is an explicit operator action:
only input prefixed with `!` is treated as a local command, and it is
executed without model involvement.

- Shell mode parses the command into argv and executes it through the
  local-process backend with `shell=False`; it does not pass input through
  a shell expansion layer.
- Shell mode is intentionally operator-initiated and receipt-anchored. It
  does not evaluate the active policy envelope before execution because the
  operator can already run the same command outside Craik. Operators who want
  shell operations subject to policy-envelope evaluation should use the
  sandbox/local-process runtime path instead of the TUI `!` prefix.
- Every invocation emits a `craik.shell_invocation_receipt` with operator
  subject, redacted command, exit code, redacted stdout/stderr previews,
  side-log hashes, working directory, duration, and a local HMAC.
- Side logs under `~/.craik/state/shell-output/` contain redacted output
  and use owner-only POSIX permissions where supported.
- Shell invocation receipts are local audit evidence, not durable remote
  attestation. Shared access to `~/.craik/` remains a compromise of local
  audit integrity.
- Contradiction and delegation queues default to records owned by the
  active operator or unassigned records. `--all` is explicit operator
  intent to inspect records owned by other operators.
- Operator text and JSON views sanitize runtime text and apply the same
  redaction boundary used by memory and receipt write paths before
  rendering terminal output or machine-readable exports.
- Receipt views surface local HMAC verification state. Verified plugin
  receipts render as verified, unsigned legacy receipts render as
  unverified, and locally tampered plugin receipts render as tampered
  when raw inspection is possible.
- The local store, session files, and receipt HMAC secrets remain local
  trust anchors. Anyone with write access to Craik home can compromise
  audit integrity, so OS account isolation remains required.

## v0.8.0 Gateway and Channel Trust Model

Craik's gateway surface is a local-first operator service, not an
open assistant endpoint. The foreground daemon is runnable with
`craik gateway start`, serves a local `/health` endpoint, writes
gateway runtime state, and uses a pid-file lock to prevent duplicate
daemon processes.

- `craik doctor`, re-running `craik setup` against existing state, and
  `craik gateway start` require an active local operator session.
- Public binds such as `0.0.0.0` and `::` require a policy envelope and
  the explicit `--allow-insecure-public-gateway` acknowledgement.
  Craik does not terminate TLS; public deployments must sit behind TLS
  termination or stay on a private network.
- Webhook ingress enforces HMAC signatures, a 1 MiB body cap, JSON
  nesting limits, timestamp freshness, accepted event replay tracking,
  and ambiguous duplicate-signature-header rejection before dispatch.
- Channel identity pairings require expiry and audit links before
  privileged ingress. Expired, revoked, unpaired, or allowlist-denied
  senders do not receive channel policy authority.
- Cron-like scheduled automations reject schedules that run more often
  than every five minutes and require policy authority before task
  creation.

## v0.12.7 Provider OAuth Trust Model

Craik's provider login surface is browser-first where provider OAuth is
usable today, and explicit about compatibility paths that rely on external
credential stores.

- Anthropic and Gemini default to OAuth when running `craik auth login`.
  OpenAI defaults to API-key capture until Craik has a registered OpenAI
  OAuth client; explicitly requesting `--mode=oauth` fails with remediation
  instead of using a placeholder client id.
- Anthropic browser bootstrap stores the resulting provider API key through
  Craik credential storage and persists a keyring-ref auth profile. The
  OAuth code and PKCE verifier are transient and are not stored in Craik
  state.
- Anthropic credentials resolve from `CLAUDE_CODE_OAUTH_TOKEN`,
  `ANTHROPIC_API_KEY`, or OS keyring. All three are sent via Anthropic's
  required `x-api-key` header. Craik reads but never writes environment
  variables; operators rotate Anthropic CLI OAuth tokens by re-running
  `claude setup-token`.
- Gemini OAuth uses Google-managed ADC or service-account credentials.
  Craik stores profile metadata such as project id, credential source, and
  service-account path, not Google refresh tokens.
- Provider OAuth state values are generated with `secrets.token_urlsafe(32)`
  and compared with `hmac.compare_digest`.
- Loopback callback helpers bind only to literal `127.0.0.1`, use an
  ephemeral port, and tear down after one callback or timeout.
- OAuth token endpoints are validated with the provider URL safety guard
  before credential-bearing refresh requests. Non-local refresh endpoints
  must use HTTPS and must not resolve to private network targets.
- Browser launch uses Python's `webbrowser.open`; Craik does not shell out
  with an operator-supplied URL.
- `scripts/check_oauth_callback_safety.py` enforces loopback bind, state
  comparison, PKCE verifier non-persistence, and refresh-token scope
  invariants in CI.
- Gateway/channel artifacts are persisted through typed local-store
  helpers: adapter contracts, identity pairings, allowlists, gateway
  receipts, schedules, scheduled automations, and channel policy
  envelopes.
- Residual limitations: Slack/Discord/email/SMS adapters, hosted
  gateway deployment, production dispatch loops, and scheduler
  supervision remain future work. Treat fixture adapters and local
  webhook helpers as controlled integration surfaces.

## v0.9.0 Persistent Agent Runtime Trust Model

Craik's persistent-agent surface keeps provider-backed sessions local,
operator-bound, and auditable. A persistent session is not a hosted
assistant endpoint; it is a local runtime record that links operator
identity, provider route, project scope, policy envelope, receipts,
handoffs, recovery state, and redacted lifecycle metadata.

- Every `craik agent ...` command requires an active local operator
  session before reading or mutating agent state. Demo commands are
  explicitly fixture-bound unless the operator passes a live override.
- Agent session state and event records carry local receipt HMAC
  integrity. Default store reads reject tampered signed records; legacy
  unsigned rows remain readable as `unverified` during the migration
  window. Resumed sessions verify before honoring persisted authority.
- Provider credential profiles and pools live under Craik home with
  owner-only permissions on POSIX systems. Credentials are referenced by
  profile id, pool id, environment variable, or secret reference; they
  are not copied into session state, receipts, logs, or CLI JSON output.
- Third-party provider requests require HTTPS base URLs with certificate
  verification enabled. Local OpenAI-compatible model endpoints may use
  plaintext HTTP only when bound to loopback (`127.0.0.1`, `localhost`,
  or `::1`); setup warns operators not to expose Ollama-style endpoints
  on non-loopback interfaces.
- Craik intentionally uses a small provider transport layer over
  published REST APIs instead of adding official OpenAI, Anthropic, or
  Gemini SDK dependencies. This narrows the dependency surface but means
  provider API changes must be tracked in Craik's adapters and tests.
- Sandbox backends enforce execution boundaries at runtime. Local
  process, Docker, SSH/remote shell, browser, and MCP paths record
  environment capability receipts; denied side effects produce explicit
  denial receipts rather than silent execution.
- The persistent-agent launch demo uses fixture transport by default
  and deletes demo session artifacts on exit. `--allow-live` and
  `--keep-artifacts` are explicit operator acknowledgements for live
  provider calls or post-demo inspection.

## v0.10.0 Interactive Shell and Credential Storage Trust Model

Craik v0.10.0 introduces an interactive agent shell (`craik`,
`craik chat`), browser-assisted provider login, credential storage
backends, profile/persona isolation, slash commands, and
operator-visible learning-loop controls. The trust boundary intent is:

- Shell launches before authentication is configured. The default shell
  reports the active readiness state without reading or mutating
  durable store state.
- `craik auth login <provider>` opens a browser to the provider's
  API-key console where applicable, prompts for the key with hidden
  terminal input, and stores the captured value in the local credential
  backend. The `AuthProfile` stores a `keyring-ref` pointer and backend
  metadata, not the credential value. Explicit `--env-var` and
  `--secret-ref` modes remain available for CI and secret-manager
  deployments.
- Credential storage backends are detected locally. OS-native secret
  stores are preferred when available. File fallback paths use
  owner-only POSIX mode, but the file content is plaintext at rest.
  Treat file fallback secrets like private keys: keep them out of
  unencrypted backups and prefer OS-native backends when available.
- `craik auth migrate-from-env` copies existing env-var profile values
  into the credential backend only after explicit consent. It does not
  mutate or unset source environment variables, and repeated runs skip
  already migrated `keyring-ref` profiles.
- v0.12.0 migration secret handling keeps adjacent-runtime secrets out
  of reports by default. Optional keyring import requires explicit
  operator confirmation and a secure OS credential backend; file
  fallback backends block import and require manual reconfiguration.
- One-shot prompts require explicit operator acknowledgment when
  supplied through argv. Prompts in argv are visible to local process
  listings and shell history. Use `craik -z -` or `craik chat -q -` to
  read from stdin; `--allow-argv-prompt` opts into argv exposure with a
  stderr warning.
- Readiness state and model listing are operator-scoped when an active
  operator session exists. Auth profiles with
  `authorized_operators` or `authorized_operator_groups` are visible
  only to matching sessions; legacy profiles without authorization
  metadata remain globally visible for compatibility. Empty authorization
  lists are invalid: use `None` for unscoped legacy visibility, or a
  non-empty list for scoped visibility.
- Slash commands inherit the same readiness and operator-session
  boundaries as the underlying runtime. Commands with side effects route
  through the existing operator identity checks before touching local
  store state.
- Profile export omits secrets by default. Profile import does not grant
  cross-profile access to credential material.
- Learning-loop authority remains operator-gated. Agents can propose
  skill improvements, but promotion rejects `agent:` approvers and
  requires an explicit operator identity plus evidence-bearing approval
  records. Rollback remains an operator action.

The standing publication policy remains unchanged: Critical and High
vulnerabilities are handled through GHSA when applicable; Medium and
Low findings are documented in this file unless a documented carve-out
applies.

## Safe Harbor

Good-faith research that avoids privacy violations, data destruction, service disruption, and public disclosure before remediation will be treated as helpful security research.
