# Release Readiness Validation

<p className="craik-meta"><span>4 min read</span><span>For maintainers</span><span>Updated 2026-05-20</span></p>

<div className="craik-lead">

**What you'll find here**

The repository-owned readiness record for Craik releases. The current release
gate is `0.2.0`; the historical `0.1.0` sign-off remains below for audit
continuity.

</div>

## v0.2.0 Release Readiness

<div className="craik-keypoint">

**Auth and identity gate.**

`0.2.0` moves Craik beyond the first provider-runtime substrate by adding
typed credential profiles, OIDC operator identity, credential pools, workload
identity federation, and receipt-backed authorization governance.

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
<dt>Credential sources</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>API-key, OAuth, CLI bridge, secret-reference, Stigmem-reference, marker, and pooled profiles are covered by store, source, and provider-runtime tests.</dd>
</div>

<div>
<dt>Operator identity</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>OIDC login, session storage, JWT validation, workload identity, and RFC 8693 exchange paths have in-repo tests, including rejection cases for unsafe token shapes.</dd>
</div>

<div>
<dt>Governance</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Receipts now carry credential and operator identity fields; policies can bind runs to credential kinds, profiles, operator subjects, groups, and issuers.</dd>
</div>

<div>
<dt>Operational safety</dt>
<dt><span className="craik-fields__type">ready</span></dt>
<dd>Credential stores use locked atomic writes, auth health appears in doctor output, first credential use is approval-gated, and per-credential redaction prevents profile-specific identifiers from leaking into artifacts.</dd>
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
uv run pytest tests/test_auth_api_key_source.py tests/test_auth_profiles.py tests/test_auth_credential_pool.py tests/test_oidc_operator.py tests/test_operator_session_store.py tests/test_workload_identity.py tests/test_oidc_exchange_secret_manager.py tests/test_provider_runtime.py tests/test_policy.py tests/test_case_files.py tests/test_handoffs.py -q
uv build
```

### v0.2.0 Security Notes

- Live provider credentials remain opt-in and are resolved from configured
  profiles at request time; raw credential material is not stored in receipts.
- Operator identity is enforced before credential resolution when policy
  requires it.
- OIDC validation rejects unsigned tokens, unknown key IDs, tampered payloads,
  and algorithm-confusion cases.
- Workload federation uses short-lived exchanged credentials and cached expiry
  margins instead of long-lived platform secrets.

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
