# Release Readiness Validation

<p className="craik-meta"><span>4 min read</span><span>For maintainers</span><span>Updated 2026-05-21</span></p>

<div className="craik-lead">

**What you'll find here**

The repository-owned readiness record for Craik releases. The current
pre-release gate is `0.6.0`; historical sign-offs remain below for
audit continuity.

</div>

## v0.6.0 Goal Workflow

<div className="craik-keypoint">

**Skills, plugins, and ecosystem foundations gate.**

`0.6.0` ships reusable skill contracts and governed plugin ecosystem
contracts without weakening Craik's no-ambient-authority runtime
model. Each goal issue shipped implementation, tests, docs, validation,
a green PR, merge, issue closure, and branch pruning before the next
goal began.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Goal issue</dd>
</div>

<div><dt>Skill package format</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/659">#659</a> · <code>craik.skill_package</code> · semantic package versions and no runtime authority</dd></div>
<div><dt>Project-scoped and global skills</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/660">#660</a> · <code>craik.skill_registry</code> · active entry and precedence invariants</dd></div>
<div><dt>Context contracts for skills</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/661">#661</a> · <code>craik.skill_invocation_context</code> · package context requirements and redacted invocation records</dd></div>
<div><dt>Plugin descriptor format</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/662">#662</a> · <code>craik.plugin_descriptor</code> · trust boundary, capabilities, docs, security notes, and compatibility</dd></div>
<div><dt>Probationary plugins</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/663">#663</a> · <code>craik.plugin_probation</code> · evidence-backed criteria and decisions before durable trust</dd></div>
<div><dt>Plugin capability grants</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/664">#664</a> · <code>craik.plugin_capability_grant</code> · explicit operations, scoped targets, approvals, expiry, and authorization helper</dd></div>
<div><dt>Plugin receipts</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/665">#665</a> · <code>craik.plugin_receipt</code> · redacted descriptor, grant, probation, evidence, and handoff links</dd></div>
<div><dt>Adapter packages</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/666">#666</a> · <code>craik.adapter_package</code> · semantic versions, runner modes, Python/platform compatibility, docs, and provenance</dd></div>
<div><dt>Reference integrations</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/667">#667</a> · <code>craik.reference_integration</code> · safe reproducible skill, plugin, and adapter examples</dd></div>
<div><dt>Community skills docs</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/668">#668</a> · package, context, registry, review, and security guidance</dd></div>
<div><dt>Community plugins docs</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/669">#669</a> · descriptors, probation, grants, receipts, adapters, references, and security guidance</dd></div>
<div><dt>Release readiness and docs assessment</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/670">#670</a> · this release record, roadmap, changelog, and release automation hygiene</dd></div>

</div>

## v0.6.0 Release Readiness

<div className="craik-keypoint">

**Ready for release prep.**

The v0.6.0 skills, plugins, and ecosystem foundations surface is
implemented in typed contracts, local-store persistence, validation
helpers, operator-visible receipt formatting, reference documentation,
and community guides. Release prep still owns the version bump,
generated docs lockfile, release heading promotion, full release
validation, tag creation, PyPI publish, docs deployment, and GitHub
Release verification.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Validation</dd>
</div>

<div>
<dt>Runtime contracts</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>skill_package</code> · <code>skill_registry</code> · <code>skill_invocation_context</code> · <code>plugin_descriptor</code> · <code>plugin_probation</code> · <code>plugin_capability_grant</code> · <code>plugin_receipt</code> · <code>adapter_package</code> · <code>reference_integration</code>.</dd>
</div>

<div>
<dt>Docs</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Reference pages and guides cover skill packages, skill registries, skill contexts, plugin descriptors, plugin probation, plugin grants, plugin receipts, adapter packages, reference integrations, community skills, and community plugins. Sidebars and index navigation include the community guides.</dd>
</div>

<div>
<dt>Validation commands</dt>
<dt><span className="craik-fields__type">passed</span></dt>
<dd>Focused slices passed across goal PRs. Final readiness validation passed <code>uv run python scripts/check_version_consistency.py</code>, <code>uv run ruff check</code>, <code>uv run mypy src</code>, <code>uv run python scripts/check_doc_links.py</code>, <code>uv run python scripts/check_public_docs_hygiene.py</code>, <code>uv run python scripts/check_release_readiness.py</code>, and full <code>uv run pytest</code> with loopback access enabled for local HTTP-server tests.</dd>
</div>

<div>
<dt>Security notes</dt>
<dt><span className="craik-fields__type">reviewed</span></dt>
<dd>Skills remain instruction packages with no runtime authority. Plugin descriptors declare needs but grant nothing. Probation blocks durable trust until evidence-backed criteria and decisions pass. Plugin grants require explicit operations, scoped targets, expiry, and approval metadata. Denied, expired, and approval-required grants do not authorize execution. Plugin receipts must be redacted and cannot mark result metadata as unredacted.</dd>
</div>

<div>
<dt>Release automation hygiene</dt>
<dt><span className="craik-fields__type">addressed</span></dt>
<dd>The publish workflow changelog extractor now accepts release headings with an em dash, en dash, or ASCII hyphen between the version and date, avoiding the v0.5.0 GitHub Release note extraction failure.</dd>
</div>

<div>
<dt>Release blocker state</dt>
<dt><span className="craik-fields__type">none known</span></dt>
<dd>The v0.6.0 milestone has no open implementation goals other than this readiness issue. No critical release blocker is known before release-prep validation.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">pending release prep</span></dt>
<dd>Release prep must bump version declarations to <code>0.6.0</code>, regenerate generated docs artifacts if required, promote the changelog heading to <code>0.6.0 — 2026-05-21</code>, run the full release validation suite, create the signed tag, publish to PyPI, verify the docs site, and verify GitHub Release creation.</dd>
</div>

</div>

## v0.5.0 Goal Workflow

<div className="craik-keypoint">

**Quality, continuity, and recovery gate.**

`0.5.0` starts with one goal issue for each roadmap capability plus a
release-readiness issue. Each issue must ship implementation, tests,
docs, and requirement validation before the milestone closes.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Goal issue</dd>
</div>

<div><dt>Recovery mode</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/636">#636</a> · <code>craik run recover</code> · <code>craik.recovery_session</code></dd></div>
<div><dt>Runtime critic</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/637">#637</a> · <code>craik.runtime_critic_finding</code></dd></div>
<div><dt>Red team mode</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/638">#638</a> · <code>craik.red_team_finding</code></dd></div>
<div><dt>Evidence coverage score</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/639">#639</a> · <code>craik.evidence_coverage_score</code></dd></div>
<div><dt>Handoff quality score</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/640">#640</a> · <code>craik.handoff_quality_score</code></dd></div>
<div><dt>Context debt tracking</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/641">#641</a> · <code>craik.context_debt_record</code></dd></div>
<div><dt>Evidence expiration rules</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/642">#642</a> · attestation and freshness expiry checks</dd></div>
<div><dt>Tool result attestation</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/643">#643</a> · <code>craik.tool_result_attestation</code></dd></div>
<div><dt>Knowledge freshness probes</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/644">#644</a> · <code>craik.knowledge_freshness_probe</code></dd></div>
<div><dt>Scratchpad with expiry</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/645">#645</a> · <code>craik.scratchpad_record</code></dd></div>
<div><dt>Known traps</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/646">#646</a> · <code>craik.known_trap</code></dd></div>
<div><dt>Negative knowledge</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/647">#647</a> · <code>craik.negative_knowledge</code></dd></div>
<div><dt>First-class unknowns</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/648">#648</a> · <code>craik.unknown_record</code></dd></div>
<div><dt>Release readiness and docs assessment</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/649">#649</a> · this release record</dd></div>
<div><dt>Structured context requests</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/650">#650</a> · <code>craik.context_request</code></dd></div>
<div><dt>Agent exit discipline</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/651">#651</a> · <code>craik.exit_discipline_check</code></dd></div>
<div><dt>What changed since last time deltas</dt><dt><span className="craik-fields__type">ready</span></dt><dd><a href="https://github.com/eidetic-labs/craik/issues/652">#652</a> · <code>craik.run_delta</code></dd></div>

</div>

## v0.5.0 Release Readiness

<div className="craik-keypoint">

**Remediated and release-ready.**

The v0.5.0 quality, continuity, and recovery surface is implemented in
typed contracts, local-store persistence, runtime helpers, operator
views, capture CLI surfaces, recovery/delta operator gates, and
reference documentation. The post-readiness remediation closed the gap
between contract definitions and production capture paths. Release prep
updates the version declarations, changelog heading, generated docs
lockfile, package verification, tag checks, PyPI publish, docs deployment
verification, and GitHub release verification.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Validation</dd>
</div>

<div>
<dt>Runtime contracts</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>recovery_session</code> · <code>run_delta</code> · <code>runtime_critic_finding</code> · <code>red_team_finding</code> · <code>handoff_quality_score</code> · <code>evidence_coverage_score</code> · <code>context_debt_record</code> · <code>tool_result_attestation</code> · <code>knowledge_freshness_probe</code> · <code>scratchpad_record</code> · <code>known_trap</code> · <code>negative_knowledge</code> · <code>unknown_record</code> · <code>context_request</code> · <code>exit_discipline_check</code>.</dd>
</div>

<div>
<dt>Operator surfaces</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Quality gate, known traps, negative knowledge, run delta, recovery, scratchpad, unknowns, context requests, context debt, critic findings, red-team findings, and exit-discipline states are formatted or captured without granting policy authority. Knowledge-resolution views distinguish unresolved records, verified receipt links, and missing or tampered receipt links.</dd>
</div>

<div>
<dt>CLI exercise path</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik knowledge</code> captures scratchpad, unknown, context-request, known-trap, and negative-knowledge records, and resolves unknown, context-request, and context-debt records with operator receipt linkage; <code>craik review</code> captures critic and red-team findings; <code>craik run recover</code> and <code>craik run delta</code> expose recovery and changed-since-last-time summaries from local durable state behind an active operator session.</dd>
</div>

<div>
<dt>Validation commands</dt>
<dt><span className="craik-fields__type">passed</span></dt>
<dd><code>uv run pytest tests/test_v0_5_0_pipeline_e2e.py</code> plus the focused readiness slice: <code>uv run pytest tests/test_recovery.py tests/test_critics.py tests/test_quality_scores.py tests/test_context_debt.py tests/test_freshness.py tests/test_known_traps.py tests/test_scratchpad.py tests/test_exit_discipline.py tests/test_operator_views.py tests/test_store.py</code>.</dd>
</div>

<div>
<dt>Security notes</dt>
<dt><span className="craik-fields__type">reviewed</span></dt>
<dd>Critic and red-team findings are non-authoritative by default; freshness and evidence-expiry checks warn or block silent reliance but do not prove truth; scratchpad content expires instead of becoming project memory; negative knowledge requires evidence and scope; resolved unknowns, fulfilled context requests, and resolved context debt require operator receipt links; tool attestations and recovery sessions carry local HMAC integrity metadata; existing recovery/delta state requires an active operator session.</dd>
</div>

<div>
<dt>Release blocker state</dt>
<dt><span className="craik-fields__type">none known</span></dt>
<dd>No critical v0.5.0 implementation blocker is known after remediation of the capture-layer readiness findings. Tagging is gated on the release-prep PR checks and version/tag validation.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">pending tag</span></dt>
<dd><code>0.5.0</code> version declarations, release notes, and docs lockfile are prepared in the release-prep branch. The release tag, PyPI package, docs deployment, and GitHub Release are verified after the release-prep PR lands.</dd>
</div>

</div>

## v0.4.0 Release Readiness

<div className="craik-keypoint">

**Runtime instruction distillation gate.**

`0.4.0` lands the declared-instruction pipeline that turns project
instruction files into typed, provenance-linked, reviewable
constraints. Sources are registered explicitly, snapshots drive stale
invalidation, extracted statements carry line/range provenance,
categories and contradiction reports keep review queues explainable,
approval receipts are required before a constraint becomes governing,
and active constraints flow into case files and compiled prompts.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Release notes</dd>
</div>

<div>
<dt>Package version</dt>
<dt><span className="craik-fields__type">shipped</span></dt>
<dd><code>pyproject.toml</code>, <code>src/craik/__init__.py</code>, <code>docs/package.json</code>, and <code>docs/package-lock.json</code> declare <code>0.4.0</code>.</dd>
</div>

<div>
<dt>Instruction source registry</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Projects can register declared instruction sources with typed source metadata, canonical paths, owner identity, path confinement, registry receipts, and project-scoped active source lists.</dd>
</div>

<div>
<dt>Source ingestion</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Markdown, Cursor rules, Codex, Copilot, and policy document sources parse into candidate statements without treating arbitrary repository Markdown as authority.</dd>
</div>

<div>
<dt>Source snapshots and stale invalidation</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Registered sources are hashed with normalized newlines and tracked as <code>new</code>, <code>unchanged</code>, <code>changed</code>, or <code>missing</code>; changed, missing, newly observed, or omitted sources defer derived proposals.</dd>
</div>

<div>
<dt>Line/range provenance</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Extracted statements persist deterministic provenance records with source ID, snapshot ID, path, line and column ranges, summaries, and excerpt hashes.</dd>
</div>

<div>
<dt>Instruction categorization</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Provenanced statements become reviewable proposals with deterministic category traceability across policy, security, boundary, command, instruction, handoff, memory, preference, and stale-risk classes.</dd>
</div>

<div>
<dt>Inter-source contradictions</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Normalized policy, boundary, command, instruction, and security-rule proposals open contradiction reports for cross-source conflicts while skipping same-source and stale deferred items.</dd>
</div>

<div>
<dt>Approval flow and receipts</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Proposals become governing only through explicit operator approval receipts; re-approval is idempotent, rejections are receipted, stale or contradicted approvals require override rationale, and active consumers exclude constraints whose approval receipt HMAC is missing or invalid.</dd>
</div>

<div>
<dt>Case-file and prompt-compilation integration</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Case files include deterministic governing distillation evidence, and compiled prompts render exactly one <code>Active instruction constraints</code> section with ordered items, provenance annotations, empty-state behavior, and stale-exclusion warnings.</dd>
</div>

<div>
<dt>Distillation CLI</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik instructions register</code>, <code>ingest</code>, <code>list</code>, <code>approve</code>, <code>reject</code>, and <code>show</code> expose source registration, pipeline execution, proposal review, approval decisions, rejection decisions, and provenance-aware item inspection through the active operator session.</dd>
</div>

<div>
<dt>Reference documentation</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>docs/reference/instruction-sources.md</code>, <code>docs/reference/distilled-instructions.md</code>, <code>docs/reference/instruction-approval.md</code>, and <code>docs/guides/managing-instructions.md</code> document the shipped v0.4.0 operator surface and link through the sidebars.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">complete</span></dt>
<dd><code>v0.4.0</code> is tagged, published to PyPI, and represented by the GitHub Release. The GitHub milestone is closed with zero open issues.</dd>
</div>

</div>

### v0.4.0 Verification Commands

Run these before release prep and again before tagging:

```bash
uv run python scripts/check_version_consistency.py
uv run python scripts/check_release_readiness.py
uv run python scripts/check_doc_links.py
uv run python scripts/check_public_docs_hygiene.py
uv run pytest tests/test_instruction_sources.py tests/test_instruction_ingestion.py tests/test_instruction_provenance.py tests/test_instruction_distillation.py tests/test_instruction_invalidation.py tests/test_instruction_contradictions.py tests/test_instruction_promotion.py tests/test_instruction_runtime_context.py tests/test_instruction_workflow_docs.py tests/test_instruction_pipeline_e2e.py tests/test_case_files.py tests/test_prompts.py tests/test_contracts.py -q
```

### v0.4.0 Security Notes

The v0.4.0 trust boundary is also documented in
[SECURITY.md](https://github.com/eidetic-labs/craik/blob/main/SECURITY.md).

- Instruction sources must be registered explicitly and remain confined
  to the registered project root before ingestion.
- Raw source files and distilled proposals are evidence, not authority;
  only governing constraints backed by approval receipts enter case
  files and compiled prompts.
- Stale or contradicted approvals require an explicit override and
  rationale, and review receipts record whether stale or contradiction
  guards were bypassed.
- Approval receipt HMACs, backed by an owner-only local secret, are
  verified before governing constraints are rendered into case files,
  onboarding context, handoffs, or compiled prompts.
- Release workflows pin GitHub Actions to immutable SHAs and attest package
  provenance before PyPI publish.
- Stale governing items are excluded from compiled prompt context and
  surfaced as distillation warnings instead of silent authority.
- Contradiction detection opens reviewable reports for cross-source
  policy, boundary, command, instruction, and security-rule conflicts.

## v0.3.0 Release Readiness

<div className="craik-keypoint">

**Multi-agent review and coordination gate.**

`0.3.0` lands the governed multi-agent surface: authenticated mailbox
messages, intent-lock coordination across simultaneous runs, structured
debate with adjudication, cross-agent review, human delegation pause and
resume, scope-change decisions, and live work-graph coordination. The same
release tightens the security boundary: identity-isolated handoff
consumption, role-allowlist dispatch, operator-bound delegation resolution,
and authenticated mailbox sends.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Release notes</dd>
</div>

<div>
<dt>Package version</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>pyproject.toml</code>, <code>src/craik/__init__.py</code>, <code>docs/package.json</code>, and <code>docs/package-lock.json</code> declare <code>0.3.0</code>.</dd>
</div>

<div>
<dt>Multi-agent messaging</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Receipt-backed <code>craik agent-message</code> and local-store helpers send and receive authenticated typed messages linked to tasks, runs, handoffs, and roles. Senders are authenticated against the run's role state, message bodies are bounded, and same-subject repeats get unique IDs instead of overwriting.</dd>
</div>

<div>
<dt>Intent-lock coordination</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Overlapping active scopes on the same project block before new loop phases or tool dispatch and persist a denial receipt, so simultaneous runs cannot race the same intent lock.</dd>
</div>

<div>
<dt>Structured debate</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>The debate runtime helper creates role-linked debate turns, summarizes agreement or disagreement, and resolves by adjudication receipt or human-delegation receipt.</dd>
</div>

<div>
<dt>Cross-agent review</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>The review protocol helper creates receipted review requests for worker results, handoffs, or debate summaries and completes them with typed findings linked back to the reviewed artifacts.</dd>
</div>

<div>
<dt>Human delegation</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Runs can be interrupted with receipted delegation requests, resolved or cancelled by CLI, and resumed from the recorded response. Resolution requires resolver operator identity and rejects attempts to resume a paused run opened by another operator.</dd>
</div>

<div>
<dt>Scope-change protocol</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Discovered work outside the current intent lock interrupts the run, records a scope-change request receipt, and exposes <code>craik scope-change decide</code> for explicit expand, sibling-task, handoff, or denial decisions before continuing.</dd>
</div>

<div>
<dt>Live work graph</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Mailbox messages, reviews, debates, delegations, and scope-change artifacts persist work-graph events that can be queried as active coordination state.</dd>
</div>

<div>
<dt>Identity isolation</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Consuming a handoff records an explicit consumer credential and operator assignment, rejects producer identity reuse by default, and requires an explicit continuation flag plus rationale when reuse is intentional.</dd>
</div>

<div>
<dt>Handoff consumption</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik task resume --from-handoff</code> creates a follow-up task, case file, and pending run that record source handoff provenance while requiring an explicit consumer credential and operator identity.</dd>
</div>

<div>
<dt>Role-based dispatch</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik run execute --role</code> records a policy-checked specialist role assignment, dispatch receipt, and run-level role metadata. Role dispatch requires explicit role allowlists and gates runner overrides behind the <code>role.runner.override</code> policy capability.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Create immutable tag <code>v0.3.0</code>, run the protected publish workflow, then verify PyPI and docs after publication.</dd>
</div>

</div>

### v0.3.0 Verification Commands

Run these before tagging:

```bash
uv run python scripts/check_version_consistency.py
uv run python scripts/check_release_version.py
uv run python scripts/check_release_readiness.py
uv run python scripts/check_release_tag.py --tag v0.3.0 --expected-version 0.3.0
uv run pytest tests/test_agent_mailbox.py tests/test_intent_lock_coordination.py tests/test_role_dispatch.py tests/test_scope_changes.py tests/integration/test_multi_agent_v030_flow.py -q
```

### v0.3.0 Security Notes

- Delegation resolution requires resolver operator identity and rejects
  attempts to resume a paused run opened by another operator.
- Mailbox sends authenticate `from_agent` against the sender run's role
  state before storing the message or receipt.
- Role dispatch requires explicit role allowlists and gates runner
  overrides behind the `role.runner.override` policy capability.
- Mailbox message bodies are bounded and repeated same-subject messages
  receive unique IDs instead of overwriting the latest message.
- Handoff consumption records an explicit consumer credential and
  operator assignment, rejects producer identity reuse by default, and
  requires an explicit continuation flag plus rationale when reuse is
  intentional.

## v0.2.0 Release Readiness

<div className="craik-keypoint">

**Durable execution continuity gate.**

`0.2.0` hardens the provider-backed loop into durable execution: resumable
phase boundaries, wall-clock and provider-token budgets, sandboxed shell tool
dispatch, run recovery commands, tool-result attestations, and local-store
migrations.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Release notes</dd>
</div>

<div>
<dt>Package version</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>pyproject.toml</code>, <code>src/craik/__init__.py</code>, <code>docs/package.json</code>, and <code>docs/package-lock.json</code> declare <code>0.2.0</code>.</dd>
</div>

<div>
<dt>Resumable execution</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Interrupted runs reopen from persisted phase outputs, stable idempotency keys prevent duplicate phase output capture, and <code>craik run resume</code> continues unfinished provider-backed runs.</dd>
</div>

<div>
<dt>Budgets</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Per-run wall-clock budgets, provider token ledgers, and pre-dispatch time checks interrupt before additional provider calls or side effects when exhausted.</dd>
</div>

<div>
<dt>Sandboxed tool execution</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Configured shell tool calls execute through the local-process sandbox backend, propagate cancellation to in-flight commands, and record hashed tool-result attestations linked to side-effect receipts.</dd>
</div>

<div>
<dt>Recovery and observability</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik run show</code>, <code>craik run cancel</code>, <code>craik run delta</code>, and persisted exit-discipline checks expose continuity state and handoff readiness.</dd>
</div>

<div>
<dt>Storage migrations</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Local-store migrations now run through a registered, forward-only framework with compatibility fixtures, ordering tests, and migration failure guidance.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Create immutable tag <code>v0.2.0</code>, run the protected publish workflow, then verify PyPI and docs after publication.</dd>
</div>

</div>

### v0.2.0 Verification Commands

Run these before tagging:

```bash
uv run python scripts/check_version_consistency.py
uv run python scripts/check_release_version.py
uv run python scripts/check_release_readiness.py
uv run python scripts/check_release_tag.py --tag v0.2.0 --expected-version 0.2.0
uv run pytest tests/test_loop.py tests/test_local_process_backend.py tests/test_loop_tool_dispatch.py tests/test_store.py tests/test_cli.py tests/test_handoffs.py tests/test_provider_runner.py -q
```

### v0.2.0 Security Notes

- Shell execution remains policy-gated and only registered command references
  are routed to the local-process sandbox backend.
- The local-process backend avoids shell expansion and propagates cancellation
  to in-flight subprocesses.
- Budget checks happen before provider calls and immediately before tool
  dispatch, preventing exhausted runs from producing new side effects.
- Tool-result attestations hash redacted replay payloads and link each
  dispatched result to its side-effect receipt.

## v0.1.0 Release Readiness

<div className="craik-keypoint">

**In-repo green.**

All in-repo readiness gates are passing. The remaining work is the
maintainer-driven `v0.1.0` tag and the protected publication workflow.

</div>

## Snapshot

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Code health</dt>
<dt><span className="craik-fields__type">green</span></dt>
<dd>CI, CodeQL, version checks, file-size budget, build, doctor all pass.</dd>
</div>

<div>
<dt>Test coverage</dt>
<dt><span className="craik-fields__type">green</span></dt>
<dd>HTTP transport, credentials, OIDC, governance, redaction, handoffs.</dd>
</div>

<div>
<dt>Security hygiene</dt>
<dt><span className="craik-fields__type">green</span></dt>
<dd>No leaked secret patterns. Operator and credential stores are file-locked, atomic, and owner-only.</dd>
</div>

<div>
<dt>Documentation</dt>
<dt><span className="craik-fields__type">green</span></dt>
<dd>Roadmap, README, changelog, limitations, mvp docs, Docusaurus build.</dd>
</div>

<div>
<dt>Operational state</dt>
<dt><span className="craik-fields__type">green</span></dt>
<dd>Milestones present. 22 issues closed for v0.1.0. No blockers open. Dependabot clear.</dd>
</div>

<div>
<dt>External release actions</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Tag and publish remain maintainer actions.</dd>
</div>

</div>

## Code health

<div className="craik-grid">

<div><h4>CI on main</h4><p>Latest <code>ci.yml</code> run on <code>main</code> completed <code>success</code>: <a href="https://github.com/eidetic-labs/craik/actions/runs/26010629626">run 26010629626</a>.</p></div>

<div><h4>CodeQL</h4><p>Latest <code>codeql.yml</code> run on <code>main</code> completed <code>success</code>: <a href="https://github.com/eidetic-labs/craik/actions/runs/26010629612">run 26010629612</a>.</p></div>

<div><h4>Code scanning</h4><p>Zero open alerts via <code>gh api repos/eidetic-labs/craik/code-scanning/alerts</code>.</p></div>

<div><h4>Version consistency</h4><p><code>uv run python scripts/check_release_version.py</code>.</p></div>

<div><h4>File-size budget</h4><p><code>find src -name "*.py" -print0 | xargs -0 uv run python scripts/check_max_file_lines.py</code>.</p></div>

<div><h4><code>craik --version</code></h4><p>Prints <code>0.1.0</code> via <code>uv run craik --version</code>.</p></div>

<div><h4><code>craik doctor</code></h4><p>Runs to completion against a fresh <code>CRAIK_HOME</code>. An entirely empty home correctly reports missing local state.</p></div>

<div><h4>Package artifacts</h4><p><code>uv build</code> produced <code>dist/craik-0.1.0.tar.gz</code> and <code>dist/craik-0.1.0-py3-none-any.whl</code>.</p></div>

</div>

## Test coverage

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Coverage</span></dt>
<dd>Test files</dd>
</div>

<div>
<dt>HTTP transport</dt>
<dt><span className="craik-fields__type">integration</span></dt>
<dd><code>tests/integration/test_http_transport_round_trip.py</code></dd>
</div>

<div>
<dt>Credential sources</dt>
<dt><span className="craik-fields__type">unit</span></dt>
<dd>API keys · local-CLI OAuth · CLI bridge · secret references · Stigmem references · marker / no-credential behavior · credential pools. Files: <code>test_auth_api_key_source.py</code>, <code>test_auth_local_cli_oauth.py</code>, <code>test_auth_cli_bridge.py</code>, <code>test_auth_secret_ref.py</code>, <code>test_auth_profiles.py</code>, <code>test_auth_credential_pool.py</code>, <code>test_provider_runtime.py</code>.</dd>
</div>

<div>
<dt>OIDC &amp; workload identity</dt>
<dt><span className="craik-fields__type">unit</span></dt>
<dd>Operator auth · session storage · GitHub Actions · Kubernetes · generic file/env tokens · RFC 8693 exchange. Files: <code>test_oidc_operator.py</code>, <code>test_operator_session_store.py</code>, <code>test_workload_identity.py</code>, <code>test_oidc_exchange_secret_manager.py</code>.</dd>
</div>

<div>
<dt>JWT hardening</dt>
<dt><span className="craik-fields__type">unit</span></dt>
<dd>Rejects <code>alg=none</code>, unknown <code>kid</code>, tampered payloads, asymmetric/symmetric confusion (<code>test_oidc_operator.py</code>).</dd>
</div>

<div>
<dt>Governance behavior</dt>
<dt><span className="craik-fields__type">unit</span></dt>
<dd>Credential-scoped receipts · operator-scoped receipts · policy-bound credentials · policy-bound operators · approval gates · expiry-as-risk · per-credential redaction · handoff identity isolation. Files: <code>test_provider_runtime.py</code>, <code>test_policy.py</code>, <code>test_loop.py</code>, <code>test_case_files.py</code>, <code>test_redaction.py</code>, <code>test_handoffs.py</code>.</dd>
</div>

</div>

**Focused readiness set:** ran the combined readiness subset with
`uv run pytest tests/integration/test_http_transport_round_trip.py
tests/test_auth_api_key_source.py tests/test_auth_local_cli_oauth.py
tests/test_auth_cli_bridge.py tests/test_auth_secret_ref.py
tests/test_auth_profiles.py tests/test_auth_credential_pool.py
tests/test_oidc_operator.py tests/test_operator_session_store.py
tests/test_workload_identity.py
tests/test_oidc_exchange_secret_manager.py
tests/test_provider_runtime.py tests/test_policy.py
tests/test_case_files.py tests/test_handoffs.py -q` — all passed.

## Security hygiene

<div className="craik-grid">

<div><h4>Secret-pattern grep</h4><p>No raw secret patterns in tests or scripts: <code>grep -rE "sk-[a-zA-Z0-9]{`{20,}`}|xoxb-|ghp_|ANTHROPIC.{`{0,5}`}=.{`{20,}`}" tests/ scripts/</code>.</p></div>

<div><h4>Operator session file</h4><p>Owner-only <code>0o600</code> writes in <code>src/craik/runtime/auth/operator/store.py</code>.</p></div>

<div><h4>Auth profiles store</h4><p><code>auth-profiles.json</code> writes are file-locked and atomic via <code>fcntl.flock</code> + tempfile + <code>os.replace</code> in <code>src/craik/runtime/auth/store.py</code>.</p></div>

<div><h4>Credential pool store</h4><p>Pool writes are file-locked and atomic in <code>src/craik/runtime/auth/pool.py</code>.</p></div>

<div><h4>Resolver errors</h4><p>Reference-level error wording such as <code>secret reference could not be resolved</code> — never raw values.</p></div>

</div>

## Documentation

<div className="craik-grid">

<div><h4>Roadmap gates</h4><p>Exactly 12 release gates <code>v0.1.0</code>–<code>v0.12.0</code>, no gaps.</p></div>

<div><h4>Roadmap auth scope</h4><p><code>docs/roadmap.md</code> states <code>v0.1.0</code> includes OIDC, pluggable credentials, operator + credential identity on receipts, policy-bound auth, approval-gated first use, expiry risk, per-credential redaction, handoff identity bookkeeping.</p></div>

<div><h4>Changelog</h4><p><code>CHANGELOG.md</code> <code>## 0.1.0 - 2026-05-17</code> narrates Phase A and Phase B.</p></div>

<div><h4>README</h4><p>"What Works Today" names OIDC and typed credential profiles.</p></div>

<div><h4>Auth on-ramp</h4><p><code>docs/guides/authentication.md</code> exists and is linked from <code>docs/index.md</code>. <code>docs/guides/quickstart.md</code> covers it.</p></div>

<div><h4>Limitations honesty</h4><p><code>docs/limitations.md</code> no longer treats shipped auth capabilities as future work.</p></div>

<div><h4>MVP docs</h4><p><code>docs/mvp.md</code> and <code>docs/mvp-roadmap.md</code> reflect the expanded <code>v0.1.0</code> scope including OIDC and credential profiles.</p></div>

<div><h4>Docs build</h4><p><code>npm run build</code> from <code>docs/</code> succeeds.</p></div>

</div>

## Operational state

<div className="craik-grid">

<div><h4>Milestones</h4><p><code>v0.1.0</code>–<code>v0.12.0</code> exist with titles matching the roadmap.</p></div>

<div><h4>v0.1.0 milestone</h4><p>22 closed issues · 0 open issues.</p></div>

<div><h4>Blockers</h4><p>No open PRs or open issues currently blocking the release.</p></div>

<div><h4>Dependabot</h4><p>Alert #1 fixed.</p></div>

<div><h4>Tag posture</h4><p>Tag <code>v0.1.0</code> does not exist locally. Tagging is a maintainer release action and should happen only after this report is accepted.</p></div>

</div>

## External release actions

<div className="craik-fields">

<div>
<dt>Action</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Create and push tag <code>v0.1.0</code></dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Maintainer action.</dd>
</div>

<div>
<dt>Run protected package publication workflow</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Maintainer action.</dd>
</div>

<div>
<dt>Optional live-provider smoke tests</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>Require real provider credentials and an operator IdP. Fixture, cassette, and in-process socket paths are already validated in-repo.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../mvp-roadmap/">
<strong>Read</strong>
<span>MVP roadmap</span>
<small>The work this readiness report validates.</small>
</a>

<a href="../limitations/">
<strong>Read</strong>
<span>Limitations</span>
<small>Honest scope after v0.1.0 ships.</small>
</a>

<a href="../security/release-process/">
<strong>Read</strong>
<span>Security release process</span>
<small>The release-day procedure for security-sensitive work.</small>
</a>

</div>
