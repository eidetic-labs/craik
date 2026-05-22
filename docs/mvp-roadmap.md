# Robust MVP Roadmap

<p className="craik-meta"><span>8 min read</span><span>For maintainers</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What's in this doc**

The release-readiness work that must land for `0.x.0` to ship as a
"robust MVP" rather than a contract-only shell. Tracking issues are
linked in each section so progress is verifiable against GitHub.

</div>

<div className="craik-keypoint">

**`0.x.0`, not `1.0.0`.**

`1.0.0` remains a later stability signal after real-world usage,
compatibility confidence, and security soak. The MVP must still
include the readiness work that affects trust, release hygiene,
documentation accuracy, provider support, and package publication.

</div>

## MVP definition

The MVP is complete when Craik can run one real software-delivery
workflow end-to-end with **OIDC-authenticated operators · typed
credential profiles · OpenAI, Anthropic, and Gemini provider support ·
policy-enforced side effects · durable receipts that name both
operator and credential identity · a useful handoff · accurate
documentation · package-release quality gates.**

The accepted proof workflow remains **Stigmem documentation and state
reconciliation**. It must run from a clean install, assemble a case
file, use a certified provider path authorized by a credential
profile, record receipts, produce a handoff, and leave memory updates
or proposals with evidence.

## Status classes

<div className="craik-fields">

<div>
<dt>Class</dt>
<dt><span className="craik-fields__type">Meaning</span></dt>
<dd>What ships</dd>
</div>

<div>
<dt><code>end-to-end</code></dt>
<dt><span className="craik-fields__type">workflow</span></dt>
<dd>Implemented as a user-facing workflow with persistence, docs, tests, and CI coverage.</dd>
</div>

<div>
<dt><code>contract/helper</code></dt>
<dt><span className="craik-fields__type">scaffolding</span></dt>
<dd>Implemented as models, evaluators, formatters, or fixtures — not as an operational workflow.</dd>
</div>

<div>
<dt><code>docs-only</code></dt>
<dt><span className="craik-fields__type">strategy</span></dt>
<dd>Documented as a product decision or strategy.</dd>
</div>

<div>
<dt><code>deferred</code></dt>
<dt><span className="craik-fields__type">post-MVP</span></dt>
<dd>Intentionally outside the first MVP.</dd>
</div>

</div>

## Execution checklist

### 0. Roadmap reset and status truth

Tracking issue: [#298](https://github.com/eidetic-labs/craik/issues/298).

- [x] Replace stale `pre-0.1.0` language in public docs.
- [x] State that the first release is `0.x.0`.
- [x] Add a surface status matrix.
- [x] Convert the release-readiness list into MVP and post-MVP buckets.

### 1. Docusaurus docs platform

Tracking issue: [#299](https://github.com/eidetic-labs/craik/issues/299).

- [x] Add a Docusaurus site.
- [x] Mirror Stigmem's `Learn` / `Build` / `Operate` / `Secure` IA.
- [x] Add local search, Mermaid support, code blocks, redirects, broken-link enforcement.
- [x] Add generated CLI/reference docs.
- [x] Add docs build CI and publish-ready Pages workflow.

### 2. Release and package foundation

Tracking issue: [#297](https://github.com/eidetic-labs/craik/issues/297).

- [x] Define `0.x.0` release cadence and tag policy.
- [x] Add version consistency checks.
- [x] Add package build verification.
- [x] Add PyPI publish workflow with protected environment.
- [x] Add changelog and release-note workflow.
- [x] Add security release process.

### 3. CI/CD parity with Stigmem

Tracking issue: [#300](https://github.com/eidetic-labs/craik/issues/300).

- [x] Split CI into path-filtered jobs.
- [x] Add lint, type, unit, contract, docs, security, and package jobs.
- [x] Add coverage baseline and ratchet.
- [x] Add changed-file strictness checks.
- [x] Add conformance suites.
- [x] Add nightly reliability workflow.
- [x] Upload test, docs, coverage, and conformance artifacts.

### 4. Persistent state migrations

Tracking issue: [#303](https://github.com/eidetic-labs/craik/issues/303).

- [x] Add local-store schema versioning.
- [x] Add forward migrations.
- [x] Add fixture databases for previous schema versions.
- [x] Add migration compatibility tests.
- [x] Add migration failure and recovery docs.

### 5. Provider runtime: OpenAI, Anthropic, and Gemini

Tracking issue: [#304](https://github.com/eidetic-labs/craik/issues/304).

- [x] Add provider abstraction for chat, streaming, tool calls, structured output, retries, errors, and usage metadata.
- [x] Implement OpenAI provider adapter.
- [x] Implement Anthropic provider adapter.
- [x] Implement Gemini provider adapter.
- [x] Store API access through typed credential profiles, credential pools, and secret references — not raw keys.
- [x] Add provider receipts and redaction behavior.
- [x] Add certification fixtures and tests for certified providers.
- [x] Verify official provider docs before implementation work that depends on live API behavior.

### 5A. Authentication, credentials, and operator identity

Tracking issue: [#464](https://github.com/eidetic-labs/craik/issues/464).

- [x] Add OIDC operator login with device-code flow and persisted sessions.
- [x] Add `craik login`, `craik logout`, `craik whoami`.
- [x] Add typed auth profiles with `<provider_family>:<name>` IDs.
- [x] Add credential sources: env-var API keys · local-CLI OAuth fallback · vendor CLI bridge · secret references · Stigmem-backed references · marker identity.
- [x] Add credential pool rotation, failover, and health tracking.
- [x] Add workload-identity providers and RFC 8693 token exchange.
- [x] Add `craik auth list / add / remove / test / status / approve / grant`.
- [x] Add credential health to `craik doctor`.
- [x] Add credential-scoped and operator-scoped receipt fields.
- [x] Add policy-bound operator and credential constraints.
- [x] Add approval-gated first live credential use.
- [x] Add credential expiry as case-file evidence and per-credential redaction.

### 6. One complete MVP runner path

Tracking issue: [#302](https://github.com/eidetic-labs/craik/issues/302).

- [x] Connect case-file assembly to prompt compilation.
- [x] Execute one provider-backed run loop.
- [x] Persist normalized runner outputs.
- [x] Create receipts for side effects and provider calls.
- [x] Produce durable handoffs on completion, block, failure, and interruption.
- [x] Add OpenAI, Anthropic, and Gemini parity checks for the MVP task path.

### 7. Policy-enforced side effects

Tracking issue: [#301](https://github.com/eidetic-labs/craik/issues/301).

- [x] Add shell-execution wrapper with grants and receipts.
- [x] Add file-write wrapper with immutable-path protection.
- [x] Add policy-gated Stigmem write wrapper.
- [x] Add guarded GitHub writes if required by the MVP proof workflow.
- [x] Add denial receipts for blocked side effects.
- [x] Add redaction regression tests for all side-effect receipts.

### 8. Stigmem and memory hardening

Tracking issue: [#305](https://github.com/eidetic-labs/craik/issues/305).

- [x] Load Stigmem facts into case files.
- [x] Load recent handoffs into case files.
- [x] Load local contradiction reports into case files.
- [x] Add direct granted Stigmem writes.
- [x] Keep proposals as the default unprivileged path.
- [x] Add memory hygiene workflow.
- [x] Preserve provenance and source-attestation metadata.

### 9. Public/internal boundary and provenance docs

Tracking issue: [#306](https://github.com/eidetic-labs/craik/issues/306).

- [x] Add public/internal boundary classifier.
- [x] Add provenance-aware documentation workflow.
- [x] Add generated-doc evidence links.
- [x] Add stale-documentation detection.
- [x] Add work-product classification.
- [x] Add decision-record suggestions.
- [x] Add CI checks preventing public docs from exposing secrets, private paths, or private task names.

### 10. MVP demo and acceptance workflow

Tracking issue: [#308](https://github.com/eidetic-labs/craik/issues/308).

- [x] Build the Stigmem docs reconciliation demo as the release acceptance path.
- [x] Include OIDC operator authentication and provider credential profile setup in the accepted workflow.
- [x] Support OpenAI and Anthropic provider execution for the demo.
- [x] Produce case file, receipts, handoff, memory proposal/write, and graph export.
- [x] Add quickstart smoke CI.
- [x] Add Docusaurus tutorial that mirrors the executable demo exactly.

### 11. Hardening and failure modes

Tracking issue: [#307](https://github.com/eidetic-labs/craik/issues/307).

- [x] Document limits and failure modes.
- [x] Add adversarial prompt-injection tests.
- [x] Add secret-leakage tests.
- [x] Add bad tool-call and policy-bypass tests.
- [x] Add timeout, retry, and budget tests.
- [x] Add contract-conformance tests for persisted payloads.

### 12. Post-MVP deferrals

Tracking issue: [#309](https://github.com/eidetic-labs/craik/issues/309).

- [x] Mark hosted gateway dispatch and broad channel adapters as post-MVP.
- [x] Mark full TUI/dashboard as post-MVP.
- [x] Mark additional live runner adapters as post-MVP.
- [x] Mark companion/mobile/visual surfaces as post-MVP.
- [x] Mark broad marketplace/community ecosystem as post-MVP.
- [x] Keep contract/helper docs honest for deferred surfaces.

## Eighteen readiness capabilities

These capabilities are addressed by the MVP roadmap rather than
deferred to a first `1.0.0` release.

<div className="craik-grid">

<div><h4>01 · Stable core schemas</h4></div>
<div><h4>02 · Persisted state migrations</h4></div>
<div><h4>03 · SemVer release process</h4></div>
<div><h4>04 · Package publication</h4></div>
<div><h4>05 · Security release process</h4></div>
<div><h4>06 · Generated CLI/reference docs</h4></div>
<div><h4>07 · Production-quality Stigmem integration</h4></div>
<div><h4>08 · Documented limits and failure modes</h4></div>
<div><h4>09 · Runnable demo</h4></div>
<div><h4>10 · Community contribution path</h4></div>
<div><h4>11 · ≥1 complete runner adapter end-to-end</h4></div>
<div><h4>12 · Policy tests in CI</h4></div>
<div><h4>13 · Public/internal boundary classifier</h4></div>
<div><h4>14 · Provenance-aware documentation</h4></div>
<div><h4>15 · Memory hygiene workflow</h4></div>
<div><h4>16 · Work product classification</h4></div>
<div><h4>17 · Decision record suggestions</h4></div>
<div><h4>18 · Learning without self-trust</h4></div>

</div>

## MVP acceptance criteria

The release ships when every criterion below holds.

- [ ] A clean install can run the accepted demo.
- [ ] The accepted demo includes operator authentication and provider credential profile setup.
- [ ] OpenAI, Anthropic, and Gemini provider paths pass certification tests.
- [ ] Provider receipts name both operator identity and credential identity.
- [ ] Side effects are policy-gated and receipt-backed.
- [ ] Redaction is applied before persistence and docs publication.
- [x] Local-store migrations are tested against fixture states.
- [ ] Docusaurus docs build with no broken links.
- [ ] CI includes lint, type, unit, docs, package, security, and conformance gates.
- [ ] Package artifacts build and can be published through a protected workflow.
- [ ] Known limitations are accurate and visible.

## What's next

<div className="craik-next">

<a href="../release-readiness/">
<strong>Snapshot</strong>
<span>Release readiness · v0.2.0</span>
<small>The concrete pass/fail checklist captured against the current main.</small>
</a>

<a href="../limitations/">
<strong>Honest scope</strong>
<span>Limitations</span>
<small>What's end-to-end today and what's scheduled for later milestones.</small>
</a>

<a href="../roadmap/">
<strong>Read</strong>
<span>Roadmap</span>
<small>The broader trajectory after the MVP ships.</small>
</a>

</div>
