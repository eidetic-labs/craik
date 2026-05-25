# Authentication and credentials

<p className="craik-meta"><span>7 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Set up operator identity, register provider credential profiles, opt
into approval-gated first-use, and bind credentials to policy. Every
provider receipt names both the human who authorized the work and the
credential that carried it.

</div>

<div className="craik-keypoint">

**Two identity axes.**

Operator identity = the human or automation driving a run. Credential
identity = the provider account behind model calls. Receipts record
both — audit answers "who authorized this" and "which credential
carried it out" without inspecting secret material.

</div>

## Operator login

Use OIDC login when a policy requires an authenticated operator.

```sh
export CRAIK_OIDC_ISSUER=https://idp.example.com
export CRAIK_OIDC_CLIENT_ID=craik-cli
craik login
craik whoami
```

`craik login` starts the CLI device-code flow, prints the verification
URL and user code, validates the returned ID token against the issuer
JWKS, and stores the session at
`<CRAIK_HOME>/operator-session.json` with owner-only permissions. The
lower-level OIDC authenticator also supports loopback + PKCE for IdPs
and entrypoints that are configured to use a browser redirect.

End the local session with:

```sh
craik logout
```

Logout removes the session file and attempts refresh-token revocation
when the issuer exposes a revocation endpoint.

## Credential profiles

Profiles live in `<CRAIK_HOME>/auth-profiles.json` and use
`<provider_family>:<name>` IDs such as `anthropic:work` or
`chat_completions:local`. Profile metadata is masked in CLI output.

### Guided setup

Use guided setup for the common provider families:

```sh
craik auth setup openai
craik auth setup anthropic
craik auth setup gemini
craik auth setup local --base-url http://localhost:11434/v1
```

The setup command writes a typed auth profile and, by default, a
single-profile credential pool. It prints redacted validation output
including credential health and missing-secret guidance. Use
`--dry-run` to validate the shape without writing state.

```sh
craik auth setup openai --dry-run
craik auth setup openai --secret-ref OPENAI_API_KEY --dry-run
```

Loopback HTTP base URLs are rejected unless the selected provider is
`local` or `--allow-local-base-url` is passed explicitly.

### Provider login

Use `craik auth login` for the default provider setup flow. Craik chooses
the strongest supported flow per provider: OpenAI uses browser PKCE OAuth
when no `OPENAI_API_KEY` is set, local-compatible providers use API-key
capture, Anthropic uses browser OAuth bootstrap, and Gemini uses
Google-managed ADC or service-account OAuth.

```sh
craik auth login openai
craik auth login anthropic
craik auth login gemini --project-id my-gcp-project
craik auth login local --base-url http://localhost:11434/v1
```

OpenAI opens a browser OAuth flow by default. Local-compatible providers, and
OpenAI when `--no-browser`, `--mode=api-key`, `--dry-run`, or an explicit
`--env-var`/`--secret-ref` is supplied, use API-key capture. In API-key mode
Craik opens the provider setup page when a browser is available, prompts for
the key with hidden terminal input, validates the shape, stores the credential
in the local credential backend, and writes a redacted `keyring-ref` profile.

Use `--mode=api-key` to force API-key capture for providers whose default is
OAuth-backed:

```sh
craik auth login anthropic --mode=api-key
craik auth login gemini --mode=api-key
```

For provider-specific OAuth endpoints, headers, setup commands, and current
support status, see
[OAuth provider reference](../reference/oauth-providers.md).

Use `--json` for automation-friendly redacted output. API-key capture can
preview the resulting profile without writing state:

```sh
craik auth login openai --json
craik auth login openai --dry-run --json
```

`craik auth status` shows the profile id, provider family, credential
kind, credential backend, last validated timestamp, and current
redacted health status. `craik auth logout <provider>` removes both the
profile and cached credential reference.

```sh
craik auth status
craik auth logout openai
```

Provider login configures provider credentials. Operator identity remains
available through `craik login` and `craik whoami`.

### OpenAI login status

OpenAI defaults to browser PKCE OAuth when `OPENAI_API_KEY` is not set:

```sh
craik auth login openai
```

The OAuth path stores access and refresh tokens in the OS keyring and routes
subsequent Craik usage through the operator's OpenAI consumer or workspace
subscription quota. The pre-flight notice explains that the OpenAI consent
screen identifies the requesting application as "Codex" because Craik uses
OpenAI's public Codex OAuth client.

Set `OPENAI_API_KEY`, pass `--no-browser`, or run
`craik auth login openai --mode=api-key` to use Platform API key billing
instead.

### Anthropic browser bootstrap

Anthropic credential sources resolve in this order:

1. `CLAUDE_CODE_OAUTH_TOKEN` environment variable from `claude setup-token`
2. `ANTHROPIC_TOKEN` environment variable for manual OAuth token overrides
3. `ANTHROPIC_API_KEY` environment variable
4. OS keyring profile from `craik auth login anthropic`

The first source that resolves wins. `craik doctor` and `craik auth status`
report which Anthropic source is active without printing credential material.

Anthropic defaults to OAuth bootstrap when no environment credential is set:

```sh
craik auth login anthropic
```

Craik opens `https://claude.ai/oauth/authorize`, asks the operator to paste
the one-time code shown by Anthropic, exchanges that code at
`https://console.anthropic.com/v1/oauth/token`, and stores the resulting
long-lived API key through Craik credential storage. Anthropic provider
requests use `x-api-key`; Anthropic rejects `Authorization: Bearer` for this
surface.

### Gemini and Vertex OAuth

Gemini defaults to Google-managed OAuth through `google-auth`.

For Application Default Credentials:

```sh
gcloud auth application-default login
craik auth login gemini --project-id my-gcp-project
```

For service accounts:

```sh
craik auth login gemini \
  --project-id my-gcp-project \
  --service-account /path/to/service-account.json
```

Craik stores the Gemini auth profile metadata, including project id and
credential source. Google-managed credential material remains in ADC or the
service-account file; Craik does not store Google refresh tokens.

<div className="craik-keypoint">

**OAuth credential material stays out of profile metadata.**

Provider OAuth profiles store handles and setup metadata, not raw tokens.
OpenAI's pending OAuth path uses separate access-token and refresh-token
handles. Anthropic bootstrap stores the resulting API key through Craik
credential storage. Gemini relies on Google-managed ADC or service-account
credentials.

</div>

### Credential storage posture

Inspect the credential backend without printing secret material:

```sh
craik auth storage status
craik auth migrate-secrets --dry-run
```

On platforms where a native keychain is not available, Craik reports the
file-backed fallback explicitly and keeps outputs redacted.

### Explicit env-var or secret-ref mode

CI and unattended deployments can keep using explicit references instead
of interactive capture:

```sh
craik auth login openai --env-var OPENAI_API_KEY
craik auth login anthropic --secret-ref ANTHROPIC_API_KEY
```

Existing v0.10.0-style env-var profiles can be migrated into cached
credential storage without modifying the source environment variables:

```sh
craik auth migrate-from-env --dry-run
craik auth migrate-from-env --apply --yes
```

The migration is idempotent. Profiles already converted to
`keyring-ref` are skipped on later runs.

### Env-var API key

```sh
export ANTHROPIC_API_KEY=...
craik auth add anthropic:work --kind=api-key --env-var=ANTHROPIC_API_KEY
craik auth test anthropic:work
```

Anthropic profiles send `x-api-key`. OpenAI and OpenAI-compatible Chat
Completions profiles send `Authorization: Bearer`.

Anthropic CLI users should use Anthropic's documented token export path:

```sh
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
craik doctor
```

<div className="craik-keypoint">

**Subscription tokens route differently.**

Subscription OAuth tokens may route to a different billing pool than
API-key provider calls. Receipts name the auth profile so operators
can distinguish the credential path used by a run.

</div>

### Other credential kinds

<div className="craik-fields">

<div>
<dt>Kind</dt>
<dt><span className="craik-fields__type">When to use</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>keyring-ref</code></dt>
<dt><span className="craik-fields__type">default interactive login</span></dt>
<dd>Created by <code>craik auth login &lt;provider&gt;</code>. The profile stores an opaque reference and backend metadata; credential material resolves through the local credential backend at request time.</dd>
</div>

<div>
<dt><code>cli-bridge</code></dt>
<dt><span className="craik-fields__type">vendor subprocess</span></dt>
<dd>Vendor tools that mint a token through a subprocess. Supports <code>stdout_json</code> and <code>stdout_line</code> extractors. Today created by writing profile metadata into <code>auth-profiles.json</code>; the CLI does not yet expose dedicated bridge flags.</dd>
</div>

<div>
<dt><code>secret-ref</code></dt>
<dt><span className="craik-fields__type">external secret manager</span></dt>
<dd>Built-in managers treat the ref as an env var name or local file path. Custom managers can implement the same resolver protocol for Vault, AWS Secrets Manager, cloud KMS brokers, or internal services.</dd>
</div>

<div>
<dt><code>stigmem-ref</code></dt>
<dt><span className="craik-fields__type">team-shared</span></dt>
<dd>Resolve credential material from a Stigmem fact (typically relation <code>craik:credential:value</code>). Metadata includes node URL · entity · optional API key · scope · relation · timeout. Supports Stigmem provenance and revocation semantics.</dd>
</div>

<div>
<dt><code>marker</code></dt>
<dt><span className="craik-fields__type">no-secret providers</span></dt>
<dd>For provider paths that intentionally need no secret (e.g., local OpenAI-compatible server). The provider receipt records a <code>&lt;provider_family&gt;:no-credential</code> marker instead of a secret-bearing profile.</dd>
</div>

</div>

## Credential pool

Use a credential pool when a provider has multiple usable accounts and
the run should rotate or fail over between them. Pools are stored in
`<CRAIK_HOME>/credential_pool.json`.

<div className="craik-grid">

<div><h4><code>round_robin</code></h4><p>Even distribution.</p></div>
<div><h4><code>failover</code></h4><p>Primary first; fall over on failure.</p></div>
<div><h4><code>weighted</code></h4><p>Weighted selection by configured priority.</p></div>
<div><h4>Per-profile health</h4><p>Tracked across calls.</p></div>

</div>

`craik auth setup` writes the default single-profile pool for guided
provider setup. More advanced pool strategies remain file-backed.

## Approval flow

<div className="craik-keypoint">

**First live use of a profile is approval-gated.**

When a run pauses with a credential approval request, approve the
profile for that run.

</div>

```sh
craik auth approve anthropic:work --run=run_123
```

The approval is recorded as a receipt. Operator-to-profile
authorization grants are also receipted:

```sh
craik auth grant anthropic:work --to-group=prod-deploy
craik auth grant anthropic:work --to-subject=operator-subject-123
```

## Workload identity

Workload identity lets CI or cloud platforms mint short-lived
credentials without storing long-lived provider secrets.

<div className="craik-fields">

<div>
<dt>Platform</dt>
<dt><span className="craik-fields__type">Source</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>GitHub Actions</dt>
<dt><span className="craik-fields__type">Actions OIDC</span></dt>
<dd>Reads <code>ACTIONS_ID_TOKEN_REQUEST_URL</code> and <code>ACTIONS_ID_TOKEN_REQUEST_TOKEN</code> from the runner.</dd>
</div>

<div>
<dt>Kubernetes</dt>
<dt><span className="craik-fields__type">projected token</span></dt>
<dd>Reads a projected service-account token from <code>/var/run/secrets/tokens/craik</code> by default.</dd>
</div>

<div>
<dt>Generic file / env-var</dt>
<dt><span className="craik-fields__type">other CI</span></dt>
<dd>Supports any CI system that exposes a current OIDC token directly.</dd>
</div>

</div>

## OIDC token exchange

The RFC 8693 token-exchange manager combines workload identity with an
external broker. Craik sends a platform-issued OIDC token to the
exchange endpoint and caches the returned short-lived credential until
expiry. A common deployment is GitHub Actions OIDC exchanged for a
provider credential that is never committed, printed, or stored as a
long-lived secret in the repo.

## Policy-bound auth

Policy envelopes can constrain both operators and credentials. This
example requires a logged-in operator from the corporate issuer,
restricts access to the `prod-deploy` group, and allows only
secret-manager-backed credentials.

```json
{
  "required_operator": true,
  "required_operator_issuer": "https://idp.example.com",
  "allowed_operator_groups": ["prod-deploy"],
  "allowed_credential_kinds": ["secret-ref"],
  "allowed_credential_profiles": ["anthropic:prod-*"]
}
```

Denied runs produce denial receipts that name the failing policy
condition without exposing credential material.

## Receipts and audit

Provider receipts include both identity dimensions:

<div className="craik-grid">

<div><h4><code>auth_profile_id</code></h4></div>
<div><h4><code>auth_kind</code></h4></div>
<div><h4><code>auth_identity_hash</code></h4></div>
<div><h4><code>operator_subject</code></h4></div>
<div><h4><code>operator_issuer</code></h4></div>
<div><h4><code>operator_email</code></h4></div>
<div><h4><code>operator_groups</code></h4></div>

</div>

The identity hash is stable across runs but non-reversible. It
supports queries like "every action taken by this operator" and "every
action carried by this credential identity" without storing the raw
credential or account identifier in the receipt.

## Health check

<div className="craik-grid">

<div><h4><code>craik auth status</code></h4><p>Stored profile state.</p></div>
<div><h4><code>craik doctor</code></h4><p>Read-only health checks · env-var presence · local credential file readability · OAuth token expiry when the source can inspect it.</p></div>

</div>

## Common failures

<div className="craik-fields">

<div>
<dt>Symptom</dt>
<dt><span className="craik-fields__type">Cause</span></dt>
<dd>Fix</dd>
</div>

<div>
<dt>Missing operator session</dt>
<dt><span className="craik-fields__type">policy</span></dt>
<dd>A policy with <code>required_operator=true</code> fails before any provider call. Run <code>craik login</code>, then retry.</dd>
</div>

<div>
<dt>Expired OAuth token</dt>
<dt><span className="craik-fields__type">credential</span></dt>
<dd>Local-CLI OAuth sources refresh when possible. If refresh cannot complete, the profile is reported as rejected or expired, and long-running case files surface token-expiry risk before the run starts.</dd>
</div>

<div>
<dt>Credential approval required</dt>
<dt><span className="craik-fields__type">first-use gate</span></dt>
<dd>Run <code>craik auth approve &lt;profile_id&gt; --run=&lt;run_id&gt;</code> to unblock the run.</dd>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../connecting-stigmem/">
<strong>Guide</strong>
<span>Connecting Stigmem</span>
<small>Configure the node URL Stigmem-backed credentials resolve against.</small>
</a>

<a href="../local-model-setup/">
<strong>Guide</strong>
<span>Local model setup</span>
<small>Configure local OpenAI-compatible providers.</small>
</a>

<a href="../../adr/credential-and-identity-architecture/">
<strong>ADR</strong>
<span>0007 · Credential and identity architecture</span>
<small>The design behind these dual identity records.</small>
</a>

<a href="../../governance/">
<strong>Read</strong>
<span>Governance</span>
<small>How policy envelopes constrain both identity dimensions.</small>
</a>

</div>
