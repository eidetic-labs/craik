# Changelog

All notable Craik release changes are tracked here. Craik's first public
release target is a robust `0.x.0` MVP; `1.0.0` remains a later compatibility
signal after real-world usage and security soak.

This project follows the shape of Keep a Changelog and uses semantic versioning
within the `0.x.0` stability expectations described in
`docs/guides/release-management.md`.

## Unreleased

### Added

- Handoff consumption workflow: `craik task resume --from-handoff` now creates
  a follow-up task, case file, and pending run that record source handoff
  provenance while requiring an explicit consumer credential and operator
  identity.

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
