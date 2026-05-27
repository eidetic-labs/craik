# OAuth Provider Reference

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-25</span></p>

<div className="craik-lead">

Craik v0.12.7 uses provider login flows that preserve the operator's intended
billing route. OpenAI and Anthropic can route through subscription-backed
credentials, while API-key paths remain available for per-token billing,
automation, and CI.

</div>

## Billing Routing At A Glance

Every credential source routes Craik usage to a specific billing surface.
Match your source to your preferred billing model:

| Provider | Source | Billing surface | Use when |
| --- | --- | --- | --- |
| **Anthropic** | `CLAUDE_CODE_OAUTH_TOKEN` env var | Claude Pro / Max subscription | You have a Claude subscription and want subscription billing |
| Anthropic | `ANTHROPIC_TOKEN` env var | Depends on the exported token | You need a manual override matching the token issuer |
| Anthropic | `ANTHROPIC_API_KEY` env var | Anthropic Console API (per-token) | You have a Console API key and want per-token billing |
| Anthropic | `CRAIK_ANTHROPIC_API_KEY` env var | Anthropic Console API (per-token) | You want a Craik-specific env-var slot |
| Anthropic | Claude CLI marker after `craik auth login anthropic` | Claude CLI subscription | You want Craik to call the local `claude` binary |
| **Gemini** | Application Default Credentials | GCP project (Vertex AI) | You use Google Cloud project billing |
| Gemini | Service-account JSON | GCP project (Vertex AI) | You need headless or organization-managed credentials |
| Gemini | `GEMINI_API_KEY` / `GOOGLE_API_KEY` env var | Google AI Studio (per-token) | You want lightweight AI Studio credentials |
| **OpenAI** | `craik auth login openai` OAuth flow | OpenAI subscription quota | You have an OpenAI consumer or workspace subscription and want subscription billing |
| OpenAI | `OPENAI_API_KEY` env var | OpenAI Platform API (per-token) | You have a Platform API key and want per-token billing |

`craik doctor` and `craik auth status` report the active billing surface for
resolved profiles so operators can verify which route their next call will use.

## OpenAI

| Field | Value |
| --- | --- |
| Authorization endpoint | `https://auth.openai.com/oauth/authorize` |
| Token endpoint | `https://auth.openai.com/oauth/token` |
| Scopes | `openid profile email offline_access` |
| Billing surface | OpenAI subscription quota or Platform API |
| v0.12.7 status | Browser PKCE OAuth and API-key login are supported |

Craik supports two OpenAI credential sources.

### 1. Platform API key (per-token billing)

```sh
export OPENAI_API_KEY=sk-...
```

Generate a key at `platform.openai.com` -> API Keys. This path is billed
per-token through the OpenAI Platform.

### 2. OpenAI subscription OAuth (subscription billing)

```sh
craik auth login openai
```

Opens a browser-based PKCE OAuth flow against `auth.openai.com`. After
operator authorization, Craik stores access and refresh tokens in the OS
keyring. Subsequent Craik usage routes through the operator's OpenAI
consumer or workspace subscription quota.

The OAuth consent screen identifies the requesting application as "Codex"
because Craik uses OpenAI's public Codex OAuth client. Craik discloses this
in the pre-flight notice before opening the browser.

If port 1455, the registered loopback callback, is in use by another
in-flight OAuth login, close that flow and retry.

### Precedence

`craik auth login openai` defaults to OAuth when the operator has not set
`OPENAI_API_KEY` and has not requested `--no-browser`. Use `--mode=api-key`,
`--no-browser`, or `OPENAI_API_KEY` to force Platform API key billing.

## Anthropic

| Field | Value |
| --- | --- |
| Claude CLI command | `claude -p` |
| Stored credential | None; Craik stores a marker profile only |
| Request header | None for `claude-cli` mode; `x-api-key` for Console API keys |
| Billing surface | Claude CLI subscription, or Anthropic Console API for direct API keys |
| Flow type | External Claude CLI delegation or direct API key |
| v0.12.7 status | Anthropic Claude CLI delegation and API-key login are supported |

Craik checks Anthropic credential sources in this order.

### 1. Claude CLI delegation

If you have Claude CLI installed and authenticated, use:

```sh
craik auth login anthropic
```

Craik stores a marker profile and calls `claude -p` for live Anthropic prompts.
It does not store or replay `CLAUDE_CODE_OAUTH_TOKEN`, which avoids routing a
Claude subscription token through Craik's third-party HTTP client.

Verify detection with:

```sh
craik doctor
craik auth status
```

### 2. Anthropic CLI OAuth token environment override

If you have Anthropic CLI installed and authenticated, reuse those
credentials through Anthropic's documented environment-variable integration:

```sh
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
```

Craik reads `CLAUDE_CODE_OAUTH_TOKEN` automatically for Anthropic requests
and sends `sk-ant-oat` tokens as bearer credentials with Claude Code beta
headers. Operators can also set `ANTHROPIC_TOKEN` as a manual OAuth token
override when they need a separately managed Anthropic token. Craik never
writes these environment variables or refreshes the token; rotate the CLI
token by re-running `claude setup-token`.

> **About Claude subscription billing:** Directly replaying
> `CLAUDE_CODE_OAUTH_TOKEN` from a third-party HTTP client may route differently
> from the first-party Claude CLI. Prefer `craik auth login anthropic`, which
> delegates to `claude -p`.

### 3. Anthropic Platform API key

Use a direct Anthropic Platform key when Anthropic CLI is not installed or when
you want a separate billing credential:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
```

Pass `--no-browser`, `--env-var`, or
`--secret-ref` with `--mode=api-key` to bypass Claude CLI and capture or
reference an Anthropic Console API key directly. `--mode=oauth` is reserved
for providers that store OAuth credentials; Anthropic's interactive browser
flow is not exposed as a supported Craik login mode.

## Gemini / Vertex AI

| Field | Value |
| --- | --- |
| Credential library | `google-auth` |
| Scope | `https://www.googleapis.com/auth/cloud-platform` |
| Billing surface | Google Cloud project |
| Flow type | Application Default Credentials or service-account JSON |
| v0.12.7 status | ADC and service-account login are supported |

For operator ADC:

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

Craik stores profile metadata such as the project id and credential source.
Google-managed credential material remains in the Google ADC or
service-account path; Craik does not store Google refresh tokens.

Use `--mode=api-key` for Gemini API-key capture through the v0.12.0
credential-storage path.
