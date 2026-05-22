# Channel Adapters

<p className="craik-meta"><span>7 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Inspect and configure Craik's first production channel boundaries for
WebChat, Telegram, Discord, and Slack without storing provider tokens
inside Craik config files.

</div>

<div className="craik-keypoint">

**Pair first, authorize second.**

Every adapter normalizes messages into the same policy-bound messaging
shape. Unknown senders remain denied until their external account is
paired to an operator subject and matched by a channel allowlist.

</div>

## Supported Adapters

<div className="craik-grid">

<div><h4>WebChat</h4><p>Local browser chat surface for dashboard-backed operator conversations.</p></div>
<div><h4>Telegram</h4><p>Bot-token adapter boundary for Telegram message updates.</p></div>
<div><h4>Discord</h4><p>Bot-token adapter boundary for Discord message events.</p></div>
<div><h4>Slack</h4><p>App-token adapter boundary for Slack event callbacks.</p></div>

</div>

Each adapter declares the same capabilities:

- `channel.message.receive`
- `channel.message.respond`

Both capabilities require grants and receipts. Inbound message text and
outbound response text are redacted from receipts.

## Setup

List the adapter contracts:

```sh
craik channels list
```

Install the default channel artifacts and print a redacted setup plan:

```sh
craik channels setup telegram
```

The setup command requires an active operator session. It persists the
adapter contract, an operator-bound bootstrap pairing, a deny-by-default
allowlist, and a channel-scoped policy envelope, then reports the
environment variable to use as a secret reference. It does not echo
token material.

<div className="craik-fields">
<div><dt>WebChat</dt><dt><span className="craik-fields__type">secret ref</span></dt><dd><code>CRAIK_WEBCHAT_TOKEN</code></dd></div>
<div><dt>Telegram</dt><dt><span className="craik-fields__type">secret ref</span></dt><dd><code>CRAIK_TELEGRAM_BOT_TOKEN</code></dd></div>
<div><dt>Discord</dt><dt><span className="craik-fields__type">secret ref</span></dt><dd><code>CRAIK_DISCORD_BOT_TOKEN</code></dd></div>
<div><dt>Slack</dt><dt><span className="craik-fields__type">secret ref</span></dt><dd><code>CRAIK_SLACK_BOT_TOKEN</code></dd></div>
</div>

Run diagnostics after adding a secret reference:

```sh
craik channels doctor slack
```

Diagnostics report whether the token resolves and whether the platform
credential backend is secure. They also report whether setup artifacts
exist in the local store. Diagnostics never print the token.

## Fixture Validation

Normalize one provider event without contacting the provider:

```sh
craik channels normalize-fixture webchat '{"message_id":"m1","user_id":"u1","text":"hello"}'
```

Build an outbound response fixture and delivery receipt:

```sh
craik channels respond-fixture telegram telegram_10 response_1 "Queued response"
```

Use `--failed` to inspect the receipt emitted for provider delivery
failure.

## Runtime Flow

1. The adapter validates provider-specific payload shape.
2. The payload is normalized into `channel = messaging` with
   provider-specific `metadata.service`.
3. The sender external id is matched against a paired
   `ChannelIdentityPairing`.
4. The event is evaluated against a deny-by-default
   `ChannelAllowlist`.
5. A channel-scoped policy envelope allows only message receive,
   response, and receipt write capabilities.
6. Inbound and outbound receipts preserve the policy id, event id,
   service, sender id, and redaction fields.

## Related

<div className="craik-grid">
<a className="craik-card" href="/docs/security/channel-adapters/"><strong>Channel Adapter Security</strong><small>Default-deny posture and token handling.</small></a>
<a className="craik-card" href="/docs/reference/channel-adapter-contract/"><strong>Adapter Contract</strong><small>Shared contract schema.</small></a>
<a className="craik-card" href="/docs/reference/channel-allowlists/"><strong>Allowlists</strong><small>Pairing and allowlist enforcement.</small></a>
<a className="craik-card" href="/docs/reference/channel-policy-envelopes/"><strong>Policy Envelopes</strong><small>Capability limits for channel ingress.</small></a>
</div>
