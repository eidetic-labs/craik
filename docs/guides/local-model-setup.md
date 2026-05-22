# Local model setup

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Configure an OpenAI-compatible local model endpoint for Craik without
putting local secrets or private host details in public docs, receipts,
or fixtures. v0.9.0 includes presets for generic OpenAI-compatible
servers, Ollama, LM Studio, and vLLM.

</div>

<div className="craik-keypoint">

**Local providers still cross a boundary.**

A loopback model server is local, but Craik still records the provider
family, base URL, auth profile, policy envelope, and receipts so later
runs can be audited.

</div>

## Guided setup

For a local OpenAI-compatible endpoint:

```sh
craik auth setup local --base-url http://localhost:11434/v1
```

The default profile id is `chat_completions:local`, and the default
credential environment variable is `LOCAL_OPENAI_COMPATIBLE_API_KEY`.
If the endpoint does not require an API key, the setup output reports
missing credential guidance, but the provider metadata can still be
used by no-secret local paths that explicitly allow that mode.

Use dry-run mode to inspect the redacted output first:

```sh
craik auth setup local --dry-run
```

## Presets

List the no-secret local routing presets:

```sh
craik provider local-presets
```

Built-in presets:

<div className="craik-fields">

<div>
<dt>Preset</dt>
<dt><span className="craik-fields__type">Default URL</span></dt>
<dd>Use for</dd>
</div>

<div>
<dt><code>openai-compatible</code></dt>
<dt><span className="craik-fields__type"><code>http://localhost:11434/v1</code></span></dt>
<dd>Any local server with an OpenAI-compatible chat completions API.</dd>
</div>

<div>
<dt><code>ollama</code></dt>
<dt><span className="craik-fields__type"><code>http://localhost:11434/v1</code></span></dt>
<dd>Ollama's OpenAI-compatible endpoint.</dd>
</div>

<div>
<dt><code>lm-studio</code></dt>
<dt><span className="craik-fields__type"><code>http://localhost:1234/v1</code></span></dt>
<dd>LM Studio local server.</dd>
</div>

<div>
<dt><code>vllm</code></dt>
<dt><span className="craik-fields__type"><code>http://localhost:8000/v1</code></span></dt>
<dd>vLLM's OpenAI-compatible server.</dd>
</div>

</div>

All presets resolve to `chat_completions` providers with local trust
boundaries, loopback-only HTTP allowance, budget/quota reference
names, and no secret references by default.

## Health checks

Check that the local server responds on the OpenAI-compatible model
listing endpoint:

```sh
craik provider local-health ollama
```

Override the URL when the server listens on another loopback port:

```sh
craik provider local-health lm-studio --base-url http://127.0.0.1:1234/v1
```

The health output reports the preset id, provider id, base URL,
status, diagnostic detail, and model ids returned by `/v1/models`.
It does not load or print third-party credentials.

## Base URL safety

Loopback HTTP is only accepted for local provider setup or when
`--allow-local-base-url` is passed intentionally. Third-party provider
profiles should use HTTPS base URLs. Setup output warns when a local
model endpoint uses plaintext HTTP; that warning is acceptable for
loopback-only servers and should be treated as unsafe if Ollama, LM
Studio, vLLM, or another local endpoint is bound to a non-loopback
interface.

## Secret references

If the local endpoint requires a token, use an environment variable or
a secret reference:

```sh
export LOCAL_OPENAI_COMPATIBLE_API_KEY=...
craik auth setup local
```

```sh
craik auth setup local \
  --secret-ref LOCAL_OPENAI_COMPATIBLE_API_KEY \
  --secret-manager env
```

CLI output prints the reference names and credential health only; it
does not print resolved credential material.

## Validation

```sh
uv run --extra dev pytest tests/test_auth_setup_cli.py
```

Expected output: guided local setup accepts loopback URLs, rejects
unsafe third-party loopback configuration, and keeps secret material
out of CLI output.

```sh
uv run --extra dev pytest tests/test_local_model_presets.py tests/test_provider_cli.py
```

Expected output: local presets resolve to no-secret provider metadata,
unsafe non-loopback HTTP URLs are rejected, health diagnostics are
clear, and CLI preset output stays redacted.
