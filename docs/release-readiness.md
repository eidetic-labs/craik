# Release Readiness Validation

<p className="craik-meta"><span>4 min read</span><span>For maintainers</span><span>Updated 2026-05-20</span></p>

<div className="craik-lead">

**What you'll find here**

The repository-owned readiness record for Craik releases. The current release
gate is `0.3.0`; historical sign-offs remain below for audit continuity.

</div>

## v0.3.0 Release Readiness

<div className="craik-keypoint">

**Multi-agent review and coordination gate.**

`0.3.0` adds governed handoff consumption, role dispatch, authenticated
mailbox messages, scope-change decisions, structured debate/adjudication, and
identity isolation for follow-up agent work.

</div>

<div className="craik-fields">

<div>
<dt>Area</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Release notes</dd>
</div>

<div>
<dt>Coordination CLI</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd><code>craik agent-message</code>, <code>craik scope-change decide</code>, <code>craik delegation</code>, and <code>craik task resume</code> expose the coordination workflows without requiring Python access.</dd>
</div>

<div>
<dt>Security posture</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Delegation resolution requires matching operator identity, mailbox senders are authenticated against run role state, role dispatch requires explicit policy allowlists, and identity continuation requires a rationale.</dd>
</div>

<div>
<dt>Reference docs</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Mailbox, scope-change, intent-lock coordination, role dispatch, and identity isolation reference pages are linked from the docs sidebar and index.</dd>
</div>

<div>
<dt>Integration coverage</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>The v0.3.0 integration test exercises two identities, role dispatch, mailbox send/receive, debate adjudication, handoff creation, and isolated handoff consumption.</dd>
</div>

<div>
<dt>Release actions</dt>
<dt><span className="craik-fields__type">pending</span></dt>
<dd>After this gate merges, bump package metadata to <code>0.3.0</code>, create immutable tag <code>v0.3.0</code>, run the protected publish workflow, then verify PyPI and docs after publication.</dd>
</div>

</div>

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
