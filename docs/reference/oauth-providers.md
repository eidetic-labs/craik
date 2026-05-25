# OAuth Provider Reference

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-25</span></p>

<div className="craik-lead">

Craik v0.12.7 uses the strongest provider login flow that is usable
without a private Craik-owned provider client registration. Anthropic and
Gemini support OAuth-backed setup today. OpenAI keeps the OAuth foundation
in place, but defaults to API-key capture until client registration is
available.

</div>

## OpenAI

| Field | Value |
| --- | --- |
| Authorization endpoint | `https://auth.openai.com/oauth/authorize` |
| Token endpoint | `https://auth.openai.com/oauth/token` |
| Scopes | `openid profile email offline_access` |
| Billing surface | OpenAI Platform API key |
| v0.12.7 status | API-key login is supported; production OAuth is pending client registration |

Use the default API-key flow:

```sh
craik auth login openai
```

`craik auth login openai --mode=oauth` exits with remediation text instead
of launching a placeholder client. Once Craik has a registered OpenAI OAuth
client, the existing OAuth profile and loopback infrastructure can be enabled
without changing the auth-profile contract.

> **About OpenAI subscription billing:** Craik currently authenticates
> against OpenAI's Platform API only, which is billed per-token regardless
> of any OpenAI consumer or workspace subscription the operator may hold.
> OpenAI has not published a third-party reuse interface for the
> subscription-billed access token its first-party clients obtain through
> their hosted sign-in flow. Tracking
> [openai/codex#10974](https://github.com/openai/codex/issues/10974) for
> the eventual published interface.

## Anthropic

| Field | Value |
| --- | --- |
| Authorization endpoint | `https://claude.ai/oauth/authorize` |
| Token endpoint | `https://console.anthropic.com/v1/oauth/token` |
| Request header | `x-api-key` |
| Billing surface | Anthropic Console account |
| Flow type | Environment token, direct API key, or OAuth-to-API-key bootstrap |
| v0.12.7 status | Anthropic CLI token env var and browser bootstrap are supported |

Craik checks Anthropic credential sources in this order.

### 1. Anthropic CLI OAuth token

If you have Anthropic CLI installed and authenticated, reuse those
credentials through Anthropic's documented environment-variable integration:

```sh
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
```

Craik reads `CLAUDE_CODE_OAUTH_TOKEN` automatically for Anthropic requests
and sends it via `x-api-key`. Operators can also set `ANTHROPIC_TOKEN` as a
manual OAuth token override when they need a separately managed Anthropic
token. Craik never writes these environment variables or refreshes the token;
rotate the CLI token by re-running `claude setup-token`.

> **About Claude subscription billing:** `CLAUDE_CODE_OAUTH_TOKEN` routes
> Craik usage through your Claude Pro or Max subscription quota. Use this
> path if you have a Claude subscription and prefer subscription billing
> over Anthropic Console per-token charges.

Verify detection with:

```sh
craik doctor
craik auth status
```

### 2. Anthropic Platform API key

Use a direct Anthropic Platform key when Anthropic CLI is not installed or when
you want a separate billing credential:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. OAuth-to-API-key bootstrap

Run the browser bootstrap when neither environment variable is set:

```sh
craik auth login anthropic
```

Craik opens the Anthropic authorization URL, asks the operator to paste the
one-time code shown by Anthropic, exchanges that code for a long-lived API
key, and stores the key through Craik credential storage. Subsequent provider
requests use Anthropic's required `x-api-key` header, not
`Authorization: Bearer`.

Use `--mode=api-key` to bypass the browser bootstrap and capture an
Anthropic API key directly.

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
