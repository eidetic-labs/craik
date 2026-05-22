# Setup Wizard

<p className="craik-meta"><span>4 min read</span><span>For first-time operators</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll do**

Run `craik setup` once to initialize the local Craik home, the local
SQLite store, and a default gateway configuration. By the end you'll
have inspectable, non-secret configuration on disk and a clear path to
adding identity, credentials, and gateway access.

</div>

## The minimal setup

```bash title="One command to get a workable Craik home"
craik setup
```

This:

- Resolves `CRAIK_HOME` (or `~/.craik/` by default).
- Creates the per-data-class subdirectories Craik writes to.
- Persists a default `craik.gateway_config` payload.
- Prints the resolved paths and next-step guidance.

<div className="craik-keypoint">

**`craik setup` is secrets-free**

The wizard writes inspectable, non-secret configuration **only**. It does
not ask for API keys, channel tokens, webhook secrets, or bearer
credentials. The `secrets_written` field in the output is always `false`.

Store secret material in your operator's secret manager or in environment
variables that the specific adapter consumes — Craik references them by
name, never copies them into config.

</div>

## What gets written

```text
$CRAIK_HOME/
  config/
    craik.toml          # user-level CLI defaults
    gateway.json        # persisted craik.gateway_config payload
  state/
    craik.sqlite        # the local store
  secrets/              # empty — operator-managed
  receipts/  handoffs/  case-files/  projects/  logs/  cache/
```

Everything in `config/` is safe to read, diff, and version. Nothing in
`config/` references a secret by value; secret references are by name only.

## Add identity and a credential profile

`craik setup` stops short of identity and credentials on purpose — those
deserve a deliberate decision. Once setup completes:

```bash title="Log in as an OIDC operator"
craik login
```

```bash title="Add a credential profile that points at an env var"
craik auth add anthropic:work \
  --kind=api-key \
  --env-var=ANTHROPIC_API_KEY
craik auth status
```

The full credential surface — local-CLI OAuth, secret-manager references,
Stigmem-backed credential references, workload identity, RFC 8693 token
exchange, approval-gated first use — lives in
[Authentication and credentials](authentication.md).

## Enable the gateway

Craik ships a gateway daemon mode for serving Slack, webhook, scheduled,
and webhook-style ingress under one governed boundary. Wire it in during
setup or any time after:

```bash title="Persist the gateway config with a policy envelope"
craik setup --enable-gateway --policy-envelope-id policy_gateway
```

For a public bind, the gateway requires an explicit policy envelope and
an explicit insecure-public override. Craik refuses to expose itself to a
non-loopback host without a policy envelope, and it fails closed unless
the operator acknowledges that TLS termination is being handled outside
Craik:

```bash title="Public bind with explicit policy"
craik setup \
  --gateway-bind-host 0.0.0.0 \
  --policy-envelope-id policy_gateway \
  --allow-insecure-public-gateway
```

The setup output prints:

<div className="craik-grid">

<div>
<h4>Resolved paths</h4>
<p><code>CRAIK_HOME</code>, state, config, and gateway file locations.</p>
</div>

<div>
<h4><code>gateway_config</code></h4>
<p>The persisted payload — including the bound policy envelope id, channel allowlists, and ingress paths.</p>
</div>

<div>
<h4><code>gateway_runtime_state</code></h4>
<p>The initial stopped lifecycle state written alongside the gateway configuration.</p>
</div>

<div>
<h4><code>secrets_written = false</code></h4>
<p>Always. Confirmation that the wizard hasn't asked for or stored secret material.</p>
</div>

<div>
<h4>Next steps</h4>
<p>Recommended commands: <code>craik doctor</code> for diagnostics, gateway review pointers, and the right docs to read before enabling channel ingress.</p>
</div>

</div>

## Run diagnostics before going live

Don't start an always-on gateway without running `craik doctor` first:

```bash title="Health-check identity, credentials, and provider posture"
craik doctor
```

Diagnostics surface unreachable credential profiles, expired tokens, bad
policy bindings, and missing gateway dependencies — every one of which is
better caught at the operator's terminal than at the gateway's first
inbound request.

## Reset and re-run

`craik setup` is idempotent. Re-running it doesn't blow away project
registrations or receipts — it re-resolves paths and updates the gateway
config when flags change. First-time setup can initialize a new home
without authentication; reconfiguring an existing local store requires an
active operator session.

To start from a clean slate:

```bash title="Start over completely"
rm -rf "$CRAIK_HOME"
craik setup
```

## What's next

<div className="craik-next">

<a href="../authentication/">
<strong>Do next</strong>
<span>Authentication &amp; credentials</span>
<small>OIDC login, credential profiles, pools, workload identity, and approval flow.</small>
</a>

<a href="../doctor/">
<strong>Diagnose</strong>
<span>Run doctor</span>
<small>Health-check the whole identity / credential / provider chain before live calls.</small>
</a>

<a href="../../reference/gateway-daemon/">
<strong>Reference</strong>
<span>Gateway daemon mode</span>
<small>The full gateway contract, channels, and ingress policy options.</small>
</a>

</div>
