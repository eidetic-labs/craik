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

## Safe Harbor

Good-faith research that avoids privacy violations, data destruction, service disruption, and public disclosure before remediation will be treated as helpful security research.
