# Local model setup

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Configure an OpenAI-compatible local model endpoint for Craik without
putting local secrets or private host details in public docs, receipts,
or fixtures.

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

## Base URL safety

Loopback HTTP is only accepted for local provider setup or when
`--allow-local-base-url` is passed intentionally. Third-party provider
profiles should use HTTPS base URLs.

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
