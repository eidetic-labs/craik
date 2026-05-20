# Identity Isolation

Multi-agent handoffs do not inherit credential or operator identity by
default. The consuming run must declare its own auth profile and
operator identity so receipts can distinguish producer authority from
consumer authority.

## Handoff Consumption

```bash
craik task resume \
  --from-handoff handoff_task_123 \
  --auth-profile-id openai:writer \
  --operator-subject operator-b \
  --operator-issuer https://idp.example.test
```

If a consumer intentionally reuses the producer identity, the operator
must pass both `--allow-identity-continuation` and
`--identity-continuation-rationale`. The rationale is recorded on the
identity-isolation receipt.

## Receipts

Identity assignment produces `handoff.identity.assign` receipts. Denial
receipts capture missing identity, implicit producer reuse, or missing
continuation rationale.
