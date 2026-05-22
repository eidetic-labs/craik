# Gateway troubleshooting

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll do**

Diagnose the v0.8.0 gateway surfaces — setup · diagnostics · channels ·
webhooks · schedules · policies · receipts — using safe commands that
don't expose secrets.

</div>

<div className="craik-keypoint">

**Gateway daemon is a roadmap surface.**

Always-on gateway daemon is a v0.8.0 capability. Setup, diagnostics,
and contracts ship earlier, but a production dispatch loop is not part
of the MVP.

</div>

## Baseline checks

```sh
craik doctor
```

Expected output: JSON with checks for local home, local store, memory
backend, gateway prerequisites, and gateway policy readiness.

```sh
craik setup --disable-gateway
```

Expected output: `secrets_written = false` and a local-only gateway
configuration. **Do not put channel tokens, webhook secrets, or bearer
credentials in Craik config payloads.**

## Setup problems

| Symptom | Check | Resolution |
| --- | --- | --- |
| Gateway config is missing | `craik doctor` reports gateway config warnings | Run `craik setup` and review the JSON output. |
| Public bind is rejected | Setup or validation reports missing policy | Add a policy envelope before using a public bind host. |
| Secrets appear in output | Review setup output and receipts | Move secrets to the provider-specific secret store and rotate exposed credentials. |

## Channel problems

| Symptom | Check | Resolution |
| --- | --- | --- |
| Message is normalized but not authorized | Inspect pairing, allowlist, and policy decisions | Pair the identity, add an allowlist rule, then select a channel policy. |
| Sender remains unpaired | Inspect channel identity pairing state | Complete an explicit pairing flow with audit links. |
| Sender was revoked | Pairing state is `revoked` | Create a new approved pairing if access should be restored. |
| Event is denied by allowlist | Decision reason is `no enabled allowlist rule matched` | Add or enable a narrow rule for the sender, workspace, thread, or metadata. |

## Webhook problems

| Symptom | Check | Resolution |
| --- | --- | --- |
| Request is invalid | Ingress reason says signature is missing or invalid | Recompute the `X-Craik-Signature` value over the raw body. |
| Body is rejected | Ingress reason says body is too large, too deep, or not a JSON object | Send a bounded JSON object with `event_id`, `event_type`, and `timestamp`. |
| Timestamp is rejected | Ingress reason says timestamp is outside the allowed window | Resend with a fresh timestamp and verify sender clock skew. |
| Event is duplicate | Ingress status is `duplicate` | Treat the event as already handled; don't dispatch twice. |
| Event type is unauthorized | Ingress status is `unauthorized` | Add the event type to the configured allowlist only if intended. |

## Schedule problems

| Symptom | Check | Resolution |
| --- | --- | --- |
| Schedule is rejected | Validation says five fields are required | Use a five-field cron-like expression. |
| Schedule token is rejected | Validation reports unsupported cron field | Use only digits, `*`, `/`, `,`, and `-`. |
| Schedule is too frequent | Validation reports the five-minute minimum | Use a minute field such as `*/5`, `*/15`, or a sparse explicit list. |
| Task is not created | Result says tick already created a task | Use the existing task for that tick. |
| Automation does not run | Result status is `disabled` | Enable the automation after reviewing policy and receipts. |
| Automation is policy denied | Result status is `policy_denied` | Add `gateway.schedule.execute` only to the intended policy envelope. |

## Policy and receipt problems

| Symptom | Check | Resolution |
| --- | --- | --- |
| Channel action is denied | Receipt status is `denied` | Inspect requested capability and channel policy boundaries. |
| Local operator capability is unavailable | Policy denies `shell.execute`, `repo.write`, or similar | Use a local operator workflow instead of channel ingress. |
| Receipt lacks payload text | `redacted_fields` includes payload fields | Expected — gateway receipts omit sensitive channel data. |
| Receipt link is missing | Check policy, channel, task, and identity ids | Recreate the gateway decision with complete context before dispatch. |

## Safe diagnostic commands

<div className="craik-grid">

<div><h4><code>craik doctor</code></h4></div>
<div><h4><code>craik setup --disable-gateway</code></h4></div>
<div><h4><code>craik update</code></h4></div>

</div>

For development validation:

```sh
uv run --extra dev ruff check .
uv run --extra dev mypy
uv run --extra dev pytest
```

<div className="craik-keypoint">

**Never paste secrets into reports.**

Do not paste webhook secrets, bearer tokens, raw message bodies, or
provider signing secrets into issue reports, public docs, or receipts.

</div>

## What's next

<div className="craik-next">

<a href="../doctor/">
<strong>Guide</strong>
<span>Doctor diagnostics</span>
<small>The first command in any gateway investigation.</small>
</a>

<a href="../../reference/gateway-daemon/">
<strong>Reference</strong>
<span>Gateway daemon mode</span>
<small>The v0.8.0 always-on gateway contract.</small>
</a>

<a href="../../reference/gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>What every channel decision records.</small>
</a>

</div>
