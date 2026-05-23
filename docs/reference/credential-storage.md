# Credential storage

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

Craik separates credential profiles from credential material. Provider
profiles live in `<CRAIK_HOME>/auth-profiles.json`; captured API keys
resolve through the credential backend named by the profile's
`keyring-ref` metadata.

## Backends

<div className="craik-fields">

<div>
<dt>Backend</dt>
<dt><span className="craik-fields__type">Platform</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>macos-keychain</code></dt>
<dt><span className="craik-fields__type">macOS</span></dt>
<dd>Used when the optional Python keyring backend is installed and available. Otherwise Craik reports the backend as unavailable and can fall back to file storage when explicitly configured.</dd>
</div>

<div>
<dt><code>windows-credential-manager</code></dt>
<dt><span className="craik-fields__type">Windows</span></dt>
<dd>Used through the optional Python keyring backend when available. Windows ACL handling is delegated to the platform credential manager.</dd>
</div>

<div>
<dt><code>secret-service</code></dt>
<dt><span className="craik-fields__type">Linux</span></dt>
<dd>Depends on the local Secret Service session and keyring backend availability. Headless Linux deployments should prefer explicit secret references or configure a supported keyring service.</dd>
</div>

<div>
<dt><code>file</code></dt>
<dt><span className="craik-fields__type">fallback</span></dt>
<dd>Stores plaintext credential values under Craik home with owner-only POSIX permissions. Use only when the operator accepts the plaintext-at-rest tradeoff.</dd>
</div>

</div>

Inspect the current backend without printing secret material:

```sh
craik auth storage status
```

## Capture-and-cache flow

`craik auth login <provider>` prompts for a provider API key, validates
that the captured value is usable for a profile, stores it through the
credential backend, and writes a redacted `keyring-ref` profile. Status
and dashboard/TUI views show the backend and health state but never the
credential value.

```sh
craik auth login openai --json
craik auth status
```

`craik auth logout <provider>` removes the profile and deletes the
cached credential reference when the profile uses `keyring-ref`.

## Migration

Use the one-time migration helper for older env-var profiles:

```sh
craik auth migrate-from-env --dry-run
craik auth migrate-from-env --apply --yes
```

The helper reads each configured env var only after consent, copies the
resolved value into the credential backend, converts the profile to
`keyring-ref`, and leaves the original environment variable untouched.
Running it again skips already migrated profiles.
