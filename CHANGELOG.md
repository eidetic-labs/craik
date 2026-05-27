# Changelog

All notable Craik release changes are tracked here. Craik's first public
release target is a robust `0.x.0` MVP; `1.0.0` remains a later compatibility
signal after real-world usage and security soak.

This project follows the shape of Keep a Changelog and uses semantic versioning
within the `0.x.0` stability expectations described in
`docs/guides/release-management.md`.

## Unreleased

### Added

- Added the local Gateway session service and `craik tui-backend --jsonl`
  transport for prompt, slash, status, progress, receipt, completion, and
  error events.
- Added `craik run prompt <prompt>` as the CLI mirror for audited raw prompt
  execution through the same Gateway path used by `/run <prompt>`.
- Added persisted model profiles alongside legacy `provider/model` selectors,
  including display labels, provider ids, backend preference, common provider
  options, and `--option key=value` passthrough knobs.
- Wired active model profile options into provider runtime requests so token
  budgets, temperature, service tier, reasoning effort, and safe passthrough
  knobs reach OpenAI, Anthropic, Chat Completions, and Gemini payloads.
- Added Gateway regression coverage for JSONL transport, model profiles,
  slash/CLI mirror policy, Claude Code marker routing, and lifecycle/progress
  events.
- Added Gateway JSONL replay fixtures and summary helpers so Textual and Rust
  TUI candidates can be evaluated against the same event contract.
- Added a Textual Gateway client path for raw prompts so the TUI consumes
  Gateway events for model selection, run lifecycle, receipts, output, and
  completion state instead of dispatching raw prompts through slash command
  internals.
- Persisted normalized Gateway event history as a redacted run output artifact
  for each audited prompt run so clients can replay run lifecycle, model,
  receipt, output, and completion evidence after execution.
- Added a Rust `ratatui` Gateway replay prototype under `crates/craik-tui-rs`
  to evaluate terminal rendering against the shared JSONL event contract.
- Expanded the Gateway JSONL protocol with `model.set`, `approval.decide`,
  and `run.interrupt` inputs plus normalized `model.changed`,
  `approval.resolved`, and `run.interrupt.requested` events.
- Added a normalized `run.working` Gateway event so TUI, JSONL, replay, and
  future channel clients can show an immediate thinking/working state before
  long provider or Claude Code execution returns.
- Added explicit CLI mirror metadata to slash command specs and regression
  coverage for backend-affecting slash commands so TUI commands stay aligned
  with non-TUI CLI entry points.
- Changed Anthropic `claude-cli` login and Claude Code execution to delegate
  through the local `claude` binary's own auth instead of storing or injecting
  `CLAUDE_CODE_OAUTH_TOKEN`, avoiding stale bearer-token failures in the TUI.
- Changed Textual `/copy` to copy the latest response or run output by default,
  with `/copy transcript` and `/copy selection` kept for full-log and selected
  row copies.
- Added `/run --backend claude-code <prompt>` for TUI-initiated audited runs
  that create Craik task, case-file, run-output, receipt, and handoff records
  while delegating execution to the local Claude Code CLI.
- Added streamed Claude Code progress events for `/run --backend claude-code`
  so the TUI transcript shows assistant and tool-use activity while a run is in
  progress.
- Added Claude Code run interruption from the TUI. `Ctrl+C` terminates the
  active Claude subprocess and records the audited run as `interrupted`;
  `/stop` and `/interrupt` request the same behavior when the composer is
  available.
- Added explicit task-scoped Claude Code run grants for repository reads,
  documentation writes, receipt writes, and verification commands, plus
  persisted raw/progress stream events so tool targets and permission denials
  remain inspectable after a run.
- Added a one-time TUI approval prompt for `/run --backend claude-code` grants.
  Approved runs now record an `approval.decide` receipt, while direct
  non-interactive dispatch must set `CRAIK_CLAUDE_CODE_RUN_APPROVED=1`.
- Added structured Claude Code activity capture for tool calls, file targets,
  shell commands, diff-like output, permission denials, and runtime approval
  requests. Runtime approval-request events are recorded as passive activity
  because the Claude Code `-p` stream path does not expose a reliable
  same-process decision channel. `/run inspect` now includes run outputs,
  receipts, and merged activity details.
- Added a live TUI run activity panel, queued prompt submissions while a run is
  active, `/run timeline`, `/mode`, selected-row transcript copy, `/copy last`,
  and `/export transcript`.

## 0.12.9 — 2026-05-26

The TUI Contract Cutover release. v0.12.8 shipped the shared command-contract
foundation; v0.12.9 completes the runtime cutover so operators actually use
that infrastructure in the shell.

### Changed

- Wired the TUI runtime to consume the CLI/TUI command contract introduced in
  v0.12.8. `textual_app.py`, `tui.py`, and `agent_shell.py` now route slash
  commands through `craik.runtime.contract.dispatch` with the shared
  `AutoSlashRegistry`.
- Cut `slash_commands.py` down to a compatibility shim over the contract
  dispatcher, removing the legacy dispatch implementation while preserving the
  import surface for existing tests and library callers.
- Switched Textual slash rendering and inline actions to the new
  `format_command_result(..., kind="tui")` renderer pipeline.
- Switched slash autocomplete, help, detail-help, argument validation,
  confirmations, result adaptation, and snapshot guards to consume
  registry-derived slash specs instead of a hand-maintained static tuple.
- Routed `interactive_prompts={}` decorator metadata into runtime behavior:
  slash dispatch now intercepts `typer.confirm` and `typer.prompt` while
  invoking decorated callbacks and hands prompt requests to the TUI.

### Added

- Added a cached TUI registry provider with shell-only slash built-ins for
  `/help`, `/clear`, `/exit`, grouped slash forms, and compatibility aliases
  that are not one-to-one Typer callbacks.
- Added canonical-composed per-command modals for provider credential capture,
  provider logout, and receipt detail display.
- Added a record-display modal primitive for read-only structured modal flows.
- Added `scripts/check_contract_dispatch_consumed.py`, a runtime-consumption
  guard that fails CI if the TUI entry points stop importing the contract
  dispatcher or reintroduce the legacy dispatcher import.
- Added `scripts/check_no_legacy_modal_pushes.py`,
  `scripts/check_no_slash_command_specs_consumption.py`, and
  `scripts/check_interactive_prompts_runtime_consumed.py` to prevent cutover
  regressions from reintroducing legacy modal pushes, deleted slash-spec APIs,
  or dead interactive-prompt metadata.
- Added end-to-end smoke coverage proving the Textual app, dependency-free TUI,
  and agent shell route slash commands through the contract dispatcher.
- Added modal-flow and structural-guard regression coverage that exercises the
  runtime path rather than only checking for static symbols.

### Fixed

- Completed the v0.12.8 CLI/TUI Contract runtime cutover. v0.12.8 shipped the
  contract infrastructure and guards, but the TUI runtime still had legacy
  dispatcher and renderer consumption paths. v0.12.9 is the strict upgrade path
  for operator-visible TUI contract behavior.

### Removed

- Removed `runtime/shell/textual_modals.py`; canonical modal modules under
  `runtime/shell/modals/` now own those flows.
- Removed `slash_command_schema.SLASH_COMMAND_SPECS` and its legacy helper
  functions; `AutoSlashRegistry` is now the slash metadata source of truth.
- Removed legacy interactive-prompt ownership comment markers; the runtime
  contract consumes declared prompt metadata directly.

## 0.12.8 — 2026-05-26

> **Errata:** v0.12.8 shipped the CLI/TUI Contract infrastructure but did not
> fully wire it into the TUI runtime. v0.12.9 completes the runtime consumption
> path and leaves v0.12.8 as a historical artifact.

### Added

- Added the v0.12.8 CLI/TUI command contract surface, with migrated
  `@craik_command` callbacks returning `CommandResult` payloads for shared
  CLI, slash-command, JSON, and TUI rendering.
- Added canonical modal metadata for prompt-backed commands and strengthened
  modal mapping checks so future prompt or confirmation call sites require
  explicit TUI ownership.
- Added structural CI guards for payload-shape validity, NextAction slash
  targets, centralized format coverage, direct stdout writes, modal mappings,
  modal security, command-result return annotations, CLI/TUI contract
  metadata, and slash snapshot coverage.
- Added canonical slash snapshots across the standard terminal-width matrix
  for table, card, and card-list command shapes.

### Changed

- Hardened migrated command output so shared callbacks emit through
  `emit_command_result()` and stay silent during slash dispatch.
- Expanded slash snapshot generation to dispatch through the canonical slash
  command registry and verify all required widths for shape-sensitive commands.
- Documented intentional legacy CLI entry points with explicit
  `craik-legacy-command:` markers and guard coverage.

### Fixed

- Fixed dual-output regressions where migrated CLI commands could write JSON
  directly instead of using the shared renderer flow.
- Fixed v0.12.8 remediation gaps F-1 through F-4: interactive prompt metadata,
  missing structural guards, snapshot-width coverage, and mixed-state command
  cleanup.

## 0.12.7 — 2026-05-25

### Added

- Added provider OAuth profile contracts, loopback PKCE safety helpers, and
  callback-safety CI coverage for browser-based provider login.
- Added Anthropic Claude CLI delegation through `craik auth login anthropic`;
  Craik stores a marker profile and calls the local `claude -p` binary instead
  of replaying Claude OAuth tokens through Craik's HTTP client.
- Added Anthropic credential resolution for `CLAUDE_CODE_OAUTH_TOKEN`, the
  documented Anthropic CLI token export path, plus `ANTHROPIC_TOKEN` for
  manual OAuth token overrides. Anthropic resolution now prefers
  `CLAUDE_CODE_OAUTH_TOKEN`, then `ANTHROPIC_TOKEN`, then
  `ANTHROPIC_API_KEY`, then stored keyring credentials, and `craik doctor` /
  `craik auth status` surface the active source without printing credential
  material.
- Added Gemini/Vertex OAuth login through Google Application Default
  Credentials and service-account JSON profiles via `google-auth`.
- Added OpenAI PKCE OAuth login against `auth.openai.com` using the public
  Codex OAuth client, with access and refresh tokens stored in the OS keyring
  and calls routed through OpenAI subscription quota.
- Added a pre-flight disclosure before OpenAI OAuth login explaining that the
  consent screen identifies the requesting application as "Codex".
- Added `craik auth login <provider> --mode=api-key`, `--mode=oauth`, and
  `--mode=claude-cli` selectors. Anthropic defaults to Claude CLI delegation
  because Anthropic does not expose a supported Craik browser OAuth flow for
  this surface. OpenAI and Gemini use OAuth-backed setup when their
  subscription or provider-managed route is available. Use `--mode=api-key` to
  force per-token API-key billing.
- Added billing-surface visibility to `craik doctor` and `craik auth status`
  so operators can verify whether a resolved credential routes to subscription
  quota, Platform API billing, Anthropic Console billing, Google AI Studio, or
  a GCP project.
- Added a billing-routing matrix to `docs/reference/oauth-providers.md`.
- Added `docs/reference/oauth-providers.md` and refreshed authentication,
  security, roadmap, and release-readiness documentation for the shipped
  provider-specific OAuth behavior.

### Security

- OAuth refresh paths validate token endpoints before resolving credential
  material and return provider-specific remediation on refresh failure.
- OAuth callback safety checks now pin loopback bind, state comparison,
  PKCE-verifier non-persistence, and refresh-token scope invariants.

## 0.12.6 — 2026-05-25

### Fixed

- Messaging channel ingress now sanitizes normalized inbound text before
  runtime boundaries.
- Slash-command registry checks now dispatch structured `/setup`,
  `/provider`, and `/status` smoke commands to prevent schema and payload
  drift.
- TUI text-selection guidance, dark/light selection styling, and
  `check_text_selection_wiring.py` now keep click-drag copy behavior
  aligned with the Textual app.

## 0.12.5 — 2026-05-24

### Fixed

- TUI readiness next-action hints now use `/login` for operator-session
  authentication while keeping `craik login` guidance on CLI surfaces.
- Release-readiness checks now reject TUI operator-login remediation that
  tells operators to exit and run `craik login`.
- Receipt verification now uses constant-time HMAC comparison and validates
  side-log digest fields as lowercase SHA-256 hex before constructing side-log
  paths.
- Slash-command error messages escape operator-supplied command names before
  rendering through the markup-enabled transcript.
- The first-launch TUI text-selection marker uses owner-only POSIX permissions.
- Bottom-of-screen dock-coverage CI guard now requires `region.y` reads to
  appear inside `assert` statements and scans all `textual_app_*.tcss` variants.
- Coverage workflow now enforces an 80% minimum overall coverage threshold
  before publishing release coverage artifacts.
- README coverage badge now renders before the release Pages coverage artifacts
  are published.

## 0.12.4 — 2026-05-24

### Added

- Added v0.12.4 command-surface ergonomics: centralized slash-command
  schema metadata, structured table/key-value/tree/Markdown rendering,
  registry drift checks, forgot-slash recovery, argument-aware help,
  current-session transcript search, receipt detail modals, overflow
  handling, toast notifications, and confirmation receipts for destructive
  TUI actions.

### Documentation

- Added `docs/guides/slash-commands.md` and refreshed terminal UI docs with
  v0.12.4 slash-command discovery, output rendering, transcript search,
  receipt detail, and confirmation behavior.

## 0.12.3 — 2026-05-23

### Added

- Added v0.12.3 terminal status-bar usage, provider quota, and
  auto-approve indicators, plus `/status` policy warning payloads for
  active auto-approve envelopes.
- Added v0.12.3 TUI input ergonomics for reverse history search, external
  editor round-trips, and multi-line input alternatives.
- Added v0.12.3 TUI shell mode via `!` commands with local-process
  execution, redacted side logs, and HMAC-signed shell invocation receipts.
- Added v0.12.3 session naming and theme controls, including `craik --name`,
  `craik tui --name`, `/rename`, `craik agent rename`, persistent agent
  `display_name`, and `/theme dark|light|monochrome`.
- Added v0.12.3 MCP discovery and CLI recovery surfaces: `/mcp`, `/mcp verbose`,
  `/mcp --json`, and command mistype suggestions for top-level and first-level
  CLI command names.

### Changed

- Provider-call usage metadata now persists to capability receipts so status and
  audit views can inspect token usage without replaying provider responses.

### Security

- Added v0.12.3 TUI shell mode via `!` commands with local-process
  execution, GitHub/provider token redaction, owner-only side-log directories,
  and HMAC-signed shell invocation receipts.

### Refined

- Refined v0.12.3 TUI aesthetics with a centralized glyph palette, low-
  contrast bottom hint bar, footer safe area, transient accent emission, and
  dot-leader transcript dividers.

### Documentation

- Documented the v0.12.3 interactive TUI
  surface, session naming, MCP discovery, mistype recovery, and audited shell
  invocation receipts.

## 0.12.2 — 2026-05-23

### Added

- Added the v0.12.2 canonical Textual TUI docs, covering bare `craik`
  interactive launch, slash-command completion, shell history scoping,
  modal auth and approval flows, transcript widgets, theme handling, and
  plain-shell fallback behavior.
- Added `docs/guides/privacy.md` with Craik's four-part data-flow model:
  zero Craik telemetry, zero third-party analytics, provider-bound prompt
  traffic, and local-only receipts, logs, and shell history.

### Changed

- Updated terminal UI documentation to reflect the current chat-first
  runtime rather than the older ASCII status display.

## 0.12.1 — 2026-05-23

### Changed

- Refined the README into a current-state product overview by removing
  planning-document inventory, MVP framing, and future-scope content.
- Hardened v0.12.1 operator UX surfaces for provider login, default
  model selection, chat readiness, gateway checks, doctor output, MCP
  config validation, and migration apply flow.
- Expanded localized shell, TUI, dashboard, and migration text coverage
  while keeping fixture schema validation stable for channel surfaces.

### Fixed

- Addressed CodeQL findings for protocol method bodies, unused auth
  aliases, Discord webhook verifier control flow, and unreachable
  verifier branches.
- Strengthened auth health-check coverage for blank secrets,
  provider-specific HTTP success paths, non-HTTP URL rejection, and
  redacted provider rejection messages.
- Migration apply now reports records without writers as skipped with
  explicit warnings instead of silently marking non-agent records as
  applied.

## 0.12.0 — 2026-05-23

### Added

- v0.12.0 adjacent runtime migration CLI through `craik migrate inspect`,
  `craik migrate plan`, and dry-run `craik migrate import`, with
  read-only JSON source discovery, text/JSON output, proposed Craik
  target mappings, and skipped secret-like field reporting that does
  not copy raw secret values.
- v0.12.0 object-level migration maps with importable, partial,
  manual, unsupported, and skipped-secret statuses for agents,
  profiles/personas, provider/model config, aliases, fallback chains,
  channels, skills, memory, sessions, schedules, sandbox, gateway, and
  approval/security posture surfaces.
- v0.12.0 migration reports through `craik migrate report`, with
  deterministic safe-to-share sections for summary counts, importable
  objects, manual actions, skipped secrets, security posture changes,
  unsupported capabilities, recommended next commands, and validation
  checklist items.
- v0.12.0 secret migration inventory and optional keyring import
  receipts, with no-copy dry-run defaults, redacted field fingerprints,
  explicit operator confirmation, and secure-backend enforcement.
- v0.12.0 adjacent runtime compatibility fixture suite covering
  provider config, model fallback, profiles/personas, channel bindings,
  sessions, memory, skills, schedules, sandbox, gateway, approval
  posture, invalid fixture handling, and secret-redaction assertions.
- v0.12.0 MCP compatibility surfaces through `craik mcp server
  manifest`, JSON-RPC smoke handling, redacted MCP client config
  import/export, and auth/policy/receipt mapping for MCP tool calls.
- v0.12.0 session portability through `craik session export-portable`
  and `import-portable`, with redacted Craik session exports,
  adjacent transcript parsing, source identity provenance, and
  unsupported tool-call reports that remain non-executable.
- v0.12.0 agent/client protocol bridge decision and first local
  adapter, with operator-auth, policy-envelope, capability-grant,
  receipt, redaction, and write-approval controls before bridged tool
  calls can execute.
- v0.12.0 i18n framework with stable message ids, configurable
  `CRAIK_LOCALE`/`--locale` text output, predictable English fallback,
  localized slash help, localized migration report headings, and
  translation contribution docs.
- v0.12.0 capture-and-cache provider auth through `craik auth login`,
  with hidden API-key prompt, `keyring-ref` profiles, backend-aware
  `auth status`, cached-credential `auth logout`, idempotent
  `auth migrate-from-env`, readiness based on credential resolvability,
  and shared slash/TUI/dashboard auth status surfaces.

### Security

- MCP client imports now reject URL schemes outside `http` and `https`
  while preserving bare stdio command references, blocking local-file and
  script-style endpoint references before routing.
- Capture-and-cache auth login now verifies captured provider credentials
  against provider model-list health endpoints with redacted failure
  details before writing cached keyring references.
- File-backed credential fallback warnings now propagate through auth
  status and doctor payloads so operators see plaintext-at-rest posture
  outside the initial login flow.
- Adjacent runtime migration scanning now enforces bounded JSON file
  counts and directory depth to avoid unbounded preflight walks.
- Auth credential-source errors are sanitized before reaching status or
  doctor output.

## 0.11.0 — 2026-05-23

### Added

- v0.11.0 terminal UI entrypoints through `craik --tui` and
  `craik tui`, with shared slash-command dispatch, multiline composer
  support, status/model/session/approval/artifact/gateway/skill panels,
  autocomplete metadata, and redacted approval modal fixtures.
- v0.11.0 authenticated local dashboard entrypoint through
  `craik dashboard`, with local-only default binding, token or active
  operator-session authorization, status/provider/session/run/handoff/
  receipt/approval/gateway/skill/model pages, shared slash-command
  action dispatch, redacted rendering, route tests, and security docs.
- v0.11.0 desktop companion MVP commands through `craik desktop`,
  including status, menu action metadata, dashboard launch action,
  gateway command actions, provider/auth health, approval notification
  deep links, doctor/update actions, redaction tests, and companion
  security docs.
- v0.11.0 gateway service lifecycle commands for install, uninstall,
  status, logs, doctor, stop, and restart, including launchd/systemd
  unit generation, Windows service-plan documentation, stale pid
  recovery, and log tailing.
- v0.11.0 real channel adapter boundaries for WebChat, Telegram,
  Discord, and Slack, including `craik channels` setup/doctor/fixture
  commands, secret-reference plans, pairing and allowlist policy gates,
  provider-specific inbound normalization, redacted outbound delivery
  receipts, and channel security docs.
- v0.11.0 approval queue UX through `/approvals` and
  `craik approvals list|show|approve|deny`, with dashboard queue
  payloads, TUI approval counts, desktop approval notification context,
  decision receipts, retry-path linkage, and approval guide docs.
- v0.11.0 product-grade diagnostics and update workflow through
  `craik doctor --fix`, explicit safe/unsafe fix planning, expanded
  operator/provider/model/gateway/channel/security posture checks,
  and `craik update --check` automation output.
- v0.11.0 multimodal and companion contracts for voice posture,
  speech-to-text, text-to-speech, multimodal artifact references,
  mobile/desktop/visual companion decisions, accessibility evidence,
  and transcript/media metadata redaction.

### Changed

- Release documentation now requires signed annotated tags plus a
  `craik-release-signing-key.asc` public-key asset on each GitHub
  Release, with fingerprint verification against the tag-signing key.
- `craik channels setup` now persists adapter contracts, identity
  pairings, allowlists, and policy envelopes; channel diagnostics now
  report persisted setup state.
- Release-readiness writer-coverage CI guard now resolves calls through
  per-module import maps using qualified function paths, eliminating
  name-collision false-greens and catching dead wrappers regardless of
  alias path. Dynamically dispatched callables use a capped
  `REGISTRY_DISPATCHED_CALLABLES` allowlist with documented rationale.
- Added complementary `scripts/check_dead_code.py` running vulture at
  confidence 80 against `src/craik`, with a curated whitelist capped at
  20 entries. It catches broader dead-code shapes the structural guard
  does not model.

### Security

- Release readiness now checks store-writer reachability through
  production wrappers, and webhook ingress receipts use the shared
  gateway channel persistence path.
- Dashboard action POSTs now enforce local Origin checks when browser
  Origin headers are present and reject mutating slash-command families
  from the generic read-only action route.
- Dashboard operator-session mode now requires
  `X-Craik-Operator-Session` to match the active session token instead
  of accepting session-file presence alone.
- Gateway service generation now writes an absolute `craik` executable
  path into launchd, systemd, and Windows service-plan output.
- Channel webhook ingress now supports platform-specific signature
  boundaries for WebChat/Craik HMAC, Slack request signatures,
  Telegram secret-token headers, and fail-closed Discord native
  signature verification when an Ed25519 verifier is unavailable.
- Local release signing-key exports are ignored by default, and
  desktop `craik://` URL-scheme guidance now requires review-only
  routing with no direct approval or mutating side effects.
- Dashboard session binding now uses a per-session random
  `dashboard_binding_token` minted at OIDC session creation, not the
  JWT `jti` claim. The JWT `jti` is no longer exposed in operator-facing
  `craik auth whoami` payloads. Existing sessions without a binding
  token must re-authenticate to use the dashboard.

### Fixed

- Gateway systemd unit generation now uses `Environment=CRAIK_EXEC=...`
  plus `ExecStart=${CRAIK_EXEC} gateway start` so resolved executable
  paths containing spaces install cleanly.
- Discord webhook signature handling now distinguishes verifier
  unavailability from invalid signatures when optional Ed25519 verifier
  libraries cannot be imported.

## 0.10.0 — 2026-05-22

### Added

- v0.10.0 interactive agent shell that can launch with `craik` or
  `craik chat` before provider or operator authentication is configured.
- Progressive setup readiness states covering unconfigured, fixture,
  local-model, operator-only, provider-only, fully-ready, and
  restricted/offline runtime postures.
- Runtime slash-command registry for setup, auth, provider, model,
  status, doctor, session, and approval guidance.
- Browser-assisted provider login for OpenAI, Anthropic, Gemini, and
  local model profiles, with secure copy/paste fallback and credential
  storage posture reporting.
- Model, session, profile, usage, and insight CLI surfaces for
  operator-facing runtime control.
- Learning-loop skill commands for telemetry, proposals, evaluation,
  promotion, rollback, and history inspection.
- Agent-shell, model/session/profile UX, readiness-state, and
  slash-command documentation.

### Changed

- The root `craik` command now opens the operator-facing shell by
  default instead of only exposing a nested command list.
- CLI reference generation now escapes MDX-sensitive angle-bracket
  placeholders in command help and option text.
- Stateful CLI release-readiness scanning now supports the split CLI
  module layout without widening bootstrap exemptions.

### Security

- Browser-assisted provider setup records no secret values in CLI
  output and reports credential-storage posture as redacted metadata.
- One-shot prompts now require stdin input (`-z -` / `chat -q -`) or
  explicit `--allow-argv-prompt` acknowledgment before accepting prompts
  visible through process listings and shell history.
- Readiness and model-listing profile enumeration now respect
  `AuthProfile.authorized_operators` and
  `authorized_operator_groups` for active operator sessions, while
  preserving legacy unscoped profile visibility.
- Auth profile metadata redaction now fails closed by exposing only
  reviewed non-secret metadata keys and masking unknown keys.
- SECURITY.md documents the v0.10.0 interactive shell and credential
  storage trust model, including the file fallback plaintext-at-rest
  caveat for secret references.
- Skill improvement controls remain proposal and approval oriented;
  agents can surface changes, but promotion and rollback stay governed
  by reviewable operator actions.

## 0.9.0 — 2026-05-22

### Added

- v0.9.0 persistent agent session contracts, lifecycle CLI, and
  provider-backed prompt execution for foreground Craik agent runs.
- Guided provider authentication setup for OpenAI, Anthropic, Gemini,
  and local model providers.
- Gemini runtime transport support and provider metadata coverage.
- Local model routing presets for Ollama, LM Studio, vLLM, and generic
  OpenAI-compatible endpoints.
- Provider certification matrix for hosted, local, and fixture-backed
  runtime routes.
- Persistent agent failure recovery for stale process state, auth
  expiry, provider errors, sandbox denials, reconnects, and resumes.
- Deterministic persistent-agent launch demo covering launch, prompt,
  receipts, handoff links, and status inspection.
- Persistent-agent security, execution-environment security, provider
  routing, local model setup, and lifecycle documentation.

### Changed

- Expanded the v0.9.0 roadmap scope to include persistent agent launch
  UX, OpenAI/Anthropic/Gemini/local provider authentication, runtime
  routing, MCP direction, sandbox backends, browser/tool boundaries,
  and environment capability receipts.
- Release-readiness validation now records the v0.9.0 goal workflow,
  milestone provenance, and auth coverage remediation before release
  prep.

### Security

- Persistent agent session state now carries HMAC integrity protection,
  with legacy unsigned rows preserved as explicit `unverified` records.
- Stateful CLI auth coverage checks now scan all `cli_*.py` modules and
  pin documented exemptions for bootstrap, demo, and CI policy-test
  flows.
- Persistent agent demos and live documentation-demo paths now require
  an operator session before using live provider transports.
- Local model provider configuration now reports plaintext HTTP
  endpoint warnings at provider write and health-check paths, not only
  during guided setup.

## 0.8.0 — 2026-05-22

### Added

- v0.8.0 gateway/channel persistence helpers for adapter contracts,
  identity pairings, allowlists, gateway receipts, schedules,
  scheduled automations, and channel policy envelopes.
- v0.8.0 foreground gateway daemon command with pid-file locking,
  `/health` serving, and persisted runtime-state transitions.
- v0.8.0 gateway pipeline coverage that validates webhook ingress,
  channel admission, policy selection, receipts, scheduling, and
  persisted gateway artifacts together.
- v0.8.0 release-readiness, roadmap, security, limitations, and
  gateway documentation reconciliation.

## 0.7.0 — 2026-05-22

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
- v0.7.0 remediation guards for operator session coverage, scoped
  operator list views, receipt HMAC status, and sanitized operator JSON
  exports.

### Changed

- Multi-project operator list commands now require an explicit
  `--project` scope instead of silently aggregating records across
  projects.
- Contradiction and delegation operator queues now default to the active
  operator plus unassigned records; `--all` is required to include other
  operators' records.

### Security

- Every read-only `craik operator` command now requires an active
  operator session before returning local-store state.
- Operator text and JSON renderers now sanitize runtime text and redact
  sensitive values before display.
- Plugin receipt inspection now gets a structured store-layer HMAC
  status, including explicit recomputation for tampered receipt display.

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
