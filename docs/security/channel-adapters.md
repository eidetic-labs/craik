# Channel Adapter Security

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

Craik's channel adapters are built as explicit trust boundaries. They
normalize external messages, bind them to identity and policy, and emit
receipts for both accepted and failed delivery paths.

</div>

## Defaults

<div className="craik-grid">

<div><h4>Deny by default</h4><p>Channel allowlists default to <code>deny</code>. Broad allow-by-default rules are rejected by the contract model.</p></div>
<div><h4>Pairing required</h4><p>External sender ids must be paired to an operator subject before privileged ingress.</p></div>
<div><h4>No token material in config</h4><p>Setup stores secret references only. Tokens come from environment or OS-backed credential paths.</p></div>
<div><h4>Receipts required</h4><p>Inbound normalization and outbound delivery both emit redacted capability receipts.</p></div>

</div>

## Token Handling

`craik channels setup <service>` requires an active operator session,
persists the adapter contract, bootstrap pairing, allowlist, and policy
envelope, and returns the expected secret reference for that service. It
does not print the token value. Keep provider tokens in the platform
keychain or an environment source managed outside the repository.

If diagnostics report a file-backed or unavailable credential backend,
restrict token files to owner-only permissions and keep them out of
backup and sync tools unless those tools provide equivalent protection.

## Sender Identity

Provider sender ids are normalized with a service prefix:

- `webchat:<user_id>`
- `telegram:<from.id>`
- `discord:<author.id>`
- `slack:<event.user>`

The prefix prevents two providers from colliding on the same external
identifier. A sender is not authorized by identity alone; it must also
match an allowlist rule for the expected workspace or thread.

## Webhook Signatures

Inbound webhooks verify the platform-native request boundary before
JSON parsing and dispatch. WebChat uses Craik's `X-Craik-Signature`
HMAC header, Slack uses `X-Slack-Signature` plus
`X-Slack-Request-Timestamp`, Telegram uses
`X-Telegram-Bot-Api-Secret-Token`, and Discord requires native
`X-Signature-Ed25519` / `X-Signature-Timestamp` verification support.
If Discord Ed25519 verification is unavailable in the runtime
environment, Discord ingress fails closed and `craik channels doctor
discord` reports the missing verifier.

## Redaction

Message text and response text are marked as redacted fields in the
adapter contracts. Receipts keep service, event id, response id,
policy id, and sender id metadata, but they do not store message body
content.

## Delivery Failure

Outbound delivery failures are not silent. The adapter emits a
`channel.message.respond` receipt with `failed` status, the redacted
provider error summary, and the policy envelope id used for the
attempt. Operators can correlate repeated failures without exposing
message content.

## Review Checklist

- Confirm each enabled adapter has a resolving secret reference.
- Confirm `craik channels setup <service>` has persisted the adapter
  contract, identity pairing, allowlist, and policy envelope.
- Confirm each sender is explicitly paired and scoped to a policy
  envelope.
- Confirm each allowlist rule has a sender, workspace, thread, service,
  or metadata selector.
- Confirm receipts are written for inbound normalization and outbound
  delivery.
- Confirm provider tokens never appear in config, docs, tests, logs, or
  receipts.
