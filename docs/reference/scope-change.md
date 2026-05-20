# Scope-Change Protocol

Scope-change requests pause work when a run discovers necessary work
outside the accepted intent lock. Operators must choose an explicit
protocol decision instead of letting the run widen scope silently.

## CLI

```bash
craik scope-change decide scope_change_123 \
  --decision expand \
  --rationale "Docs examples are required for acceptance." \
  --decided-by operator-a \
  --run-id run_123
```

Supported decisions:

- `expand`: create a new expanded intent lock and attach it to the run.
- `sibling`: create a follow-up sibling task.
- `handoff`: link existing handoffs to the request.
- `denied`: reject the scope expansion.

## Resume Safety

Resumed loops reload the run's persisted `intent_lock_id` before
checking scope. That prevents a stale in-memory lock from bypassing
peer-run coordination or scope-overlap checks after an operator has
accepted an expansion.

## Receipts

Requests record `scope_change.request` receipts. Decisions record
`scope_change.decide` receipts with the decision, rationale, updated
intent lock, sibling task, and handoff references.
